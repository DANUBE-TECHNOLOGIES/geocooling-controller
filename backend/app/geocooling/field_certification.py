from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class GeoCoolingFieldCertification:
    """Persistent, non-invasive field wiring certification workflow."""

    VERSION = "H024-FIELD-CERTIFICATION-1.0"
    REQUIRED_CHECKS = (
        "power_supplies_verified",
        "protective_earth_verified",
        "valve_relay_wiring_verified",
        "pump_relay_wiring_verified",
        "manual_safe_state_verified",
        "sensor_labels_verified",
        "emergency_stop_verified",
    )

    def __init__(self, readiness: Any, journal: Any, path: str | None = None) -> None:
        self.readiness = readiness
        self.journal = journal
        base = Path(os.getenv("GEOCOOLING_DATA_DIR", "/app/data/geocooling"))
        self.path = Path(path or os.getenv("GEOCOOLING_FIELD_CERTIFICATION_PATH", str(base / "field-certification.json")))
        self.last_certificate: dict[str, Any] | None = None
        self.history: list[dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data.get("last_certificate"), dict):
                self.last_certificate = data["last_certificate"]
            if isinstance(data.get("history"), list):
                self.history = data["history"][-100:]
        except Exception:
            return

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(json.dumps({"last_certificate": self.last_certificate, "history": self.history[-100:]}, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)
        except Exception:
            pass

    def status(self) -> dict[str, Any]:
        return {
            "generated_at": utc_now_iso(), "version": self.VERSION,
            "required_checks": list(self.REQUIRED_CHECKS),
            "last_certificate": self.last_certificate,
            "certified": bool(self.last_certificate and self.last_certificate.get("status") == "PASS"),
            "activation_allowed": False, "automatic_execution_allowed": False, "hardware_touched": False,
        }

    def evaluate(self, payload: dict[str, Any]) -> dict[str, Any]:
        operator = str(payload.get("operator") or "").strip()
        site = str(payload.get("site") or "GeoCooling installation").strip()
        if not operator:
            raise ValueError("operator is required")
        acknowledgements = payload.get("checks")
        if not isinstance(acknowledgements, dict):
            raise ValueError("checks must be an object")
        readiness = self.readiness.status()
        checks = [{"name": name, "pass": acknowledgements.get(name) is True} for name in self.REQUIRED_CHECKS]
        checks.append({"name": "software_readiness_pass", "pass": readiness.get("status") == "PASS"})
        passed = all(item["pass"] for item in checks)
        issued_at = utc_now_iso()
        certificate_core = {
            "version": self.VERSION, "issued_at": issued_at, "operator": operator, "site": site,
            "status": "PASS" if passed else "FAIL", "checks": checks,
            "readiness_snapshot": readiness,
            "notes": str(payload.get("notes") or "").strip(),
            "activation_allowed": False, "automatic_execution_allowed": False, "hardware_touched": False,
        }
        digest = hashlib.sha256(json.dumps(certificate_core, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
        certificate = {"certificate_id": f"H024-{digest[:16].upper()}", "sha256": digest, **certificate_core}
        self.last_certificate = certificate
        self.history.append(certificate)
        self._save()
        self.journal.record("field-certification", "evaluated", level="INFO" if passed else "WARNING", details=certificate)
        return certificate

    def certificates(self, limit: int = 20) -> list[dict[str, Any]]:
        return list(reversed(self.history[-limit:]))
