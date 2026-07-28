from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name, "true" if default else "false")
    return value.strip().lower() in {"1", "true", "yes", "on"}


class GeoCoolingHardwareReadiness:
    """Pre-activation hardware readiness evaluator.

    This service is intentionally non-invasive: it inspects configuration and
    gateway state, generates an expected relay sequence, and never arms or
    writes to physical hardware.
    """

    VERSION = "H023-HARDWARE-READINESS-1.0"

    def __init__(self, gateway: Any, safety: Any, journal: Any) -> None:
        self.gateway = gateway
        self.safety = safety
        self.journal = journal

    def status(self) -> dict[str, Any]:
        hardware = self.gateway.status()
        safety = self.safety.status()
        device = hardware.get("device") or {}
        mode = str(hardware.get("gateway_mode") or "simulation")
        valve_relay = int(device.get("valve_relay") or os.getenv("GEOCOOLING_WAVESHARE_VALVE_RELAY", "1"))
        pump_relay = int(device.get("pump_relay") or os.getenv("GEOCOOLING_WAVESHARE_PUMP_RELAY", "2"))
        host = str(device.get("host") or os.getenv("GEOCOOLING_WAVESHARE_HOST", "192.168.10.200"))
        port = int(device.get("port") or os.getenv("GEOCOOLING_WAVESHARE_PORT", "502"))
        unit_id = int(device.get("unit_id") or os.getenv("GEOCOOLING_WAVESHARE_UNIT_ID", "1"))
        hardware_armed_env = env_bool("GEOCOOLING_HARDWARE_ARMED", False)

        checks = [
            {"name": "gateway-mode-explicit", "pass": mode in {"simulation", "waveshare"}, "value": mode},
            {"name": "relay-mapping-valid", "pass": 1 <= valve_relay <= 8 and 1 <= pump_relay <= 8 and valve_relay != pump_relay,
             "value": {"valve_relay": valve_relay, "pump_relay": pump_relay}},
            {"name": "network-target-valid", "pass": bool(host.strip()) and 1 <= port <= 65535 and 0 <= unit_id <= 247,
             "value": {"host": host, "port": port, "unit_id": unit_id}},
            {"name": "driver-disarmed", "pass": not bool(hardware.get("armed")), "value": bool(hardware.get("armed"))},
            {"name": "environment-disarmed", "pass": not hardware_armed_env, "value": hardware_armed_env},
            {"name": "outputs-safe", "pass": not bool(hardware.get("valve_open")) and not bool(hardware.get("pump_running")),
             "value": {"valve_open": bool(hardware.get("valve_open")), "pump_running": bool(hardware.get("pump_running"))}},
            {"name": "safety-clear", "pass": not bool(safety.get("emergency_stop")), "value": safety.get("emergency_stop")},
        ]
        passed = sum(bool(item["pass"]) for item in checks)
        physical_probe_possible = mode == "waveshare"
        return {
            "generated_at": utc_now_iso(),
            "version": self.VERSION,
            "status": "PASS" if passed == len(checks) else "FAIL",
            "score_percent": round(100 * passed / len(checks), 1),
            "checks": checks,
            "gateway_mode": mode,
            "physical_probe_possible": physical_probe_possible,
            "activation_preconditions_met": passed == len(checks) and physical_probe_possible,
            "activation_allowed": False,
            "automatic_execution_allowed": False,
            "hardware_touched": False,
        }

    def dry_run_sequence(self) -> dict[str, Any]:
        readiness = self.status()
        commands = ["SAFE_STATE", "OPEN_VALVE", "START_PUMP", "STOP_PUMP", "CLOSE_VALVE", "SAFE_STATE"]
        results = [self.gateway.dry_run(command) for command in commands]
        accepted = all(bool(item.get("accepted")) for item in results)
        report = {
            "generated_at": utc_now_iso(),
            "version": self.VERSION,
            "status": "PASS" if readiness["status"] == "PASS" and accepted else "FAIL",
            "readiness": readiness,
            "sequence": results,
            "expected_invariants": [
                "pump may start only after valve open",
                "pump stops before valve closes",
                "final state is pump OFF and valve CLOSED",
            ],
            "activation_allowed": False,
            "automatic_execution_allowed": False,
            "hardware_touched": False,
        }
        self.journal.record("hardware-readiness", "dry_run_sequence", level="INFO" if report["status"] == "PASS" else "WARNING", details=report)
        return report
