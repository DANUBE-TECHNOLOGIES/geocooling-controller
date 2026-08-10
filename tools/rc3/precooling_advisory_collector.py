#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import signal
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

REPO = Path(os.getenv("GEOCOOLING_REPO", "/opt/stacks/smart-building-controller"))
DATA_ROOT = REPO / "rc3-precooling-journal"
ACTIVE_FILE = DATA_ROOT / ".active-session"
STOP_FILE = DATA_ROOT / ".stop"

BASE_URL = os.getenv("GEOCOOLING_INTERNAL_API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
INTERVAL_SECONDS = max(60, int(os.getenv("GEOCOOLING_PRECOOL_JOURNAL_INTERVAL_SECONDS", "300")))

running = True


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def stop_handler(signum: int, frame: Any) -> None:
    global running
    running = False


def get_json(route: str) -> dict[str, Any]:
    request = Request(
        BASE_URL + route,
        method="GET",
        headers={"Accept": "application/json", "User-Agent": "GeoCooling-PreCooling-Journal/1.0"},
    )
    with urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("JSON root must be an object")
    return payload


def main() -> int:
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    session = DATA_ROOT / datetime.now().strftime("session-%Y%m%d-%H%M%S")
    session.mkdir(parents=True, exist_ok=False)
    ACTIVE_FILE.write_text(str(session), encoding="utf-8")
    STOP_FILE.unlink(missing_ok=True)

    metadata = {
        "schema": "geocooling.rc35.precooling-journal.v1",
        "started_at": now_iso(),
        "interval_seconds": INTERVAL_SECONDS,
        "advisory_route": "/geocooling/rc3/weather-inertia/precooling-advisory",
        "prediction_route": "/geocooling/rc3/weather-inertia/live",
        "context_route": "/geocooling/decision-context/live",
        "http_methods_used": ["GET"],
        "controller_authorized": False,
        "hardware_write": False,
        "mqtt_publish": False,
        "database_write": False,
        "pid": os.getpid(),
    }

    metadata_file = session / "metadata.json"
    metadata_file.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    snapshots_file = session / "precooling-snapshots.jsonl"
    errors_file = session / "errors.log"

    signal.signal(signal.SIGTERM, stop_handler)
    signal.signal(signal.SIGINT, stop_handler)
    samples = 0

    try:
        while running and not STOP_FILE.exists():
            started = time.monotonic()
            try:
                advisory = get_json("/geocooling/rc3/weather-inertia/precooling-advisory")
                prediction = get_json("/geocooling/rc3/weather-inertia/live")
                context = get_json("/geocooling/decision-context/live")

                snapshot = {
                    "schema": "geocooling.rc35.precooling-snapshot.v1",
                    "captured_at": now_iso(),
                    "advisory": advisory,
                    "prediction": prediction,
                    "context": context,
                    "safety": {
                        "controller_authorized": False,
                        "hardware_write": False,
                        "mqtt_publish": False,
                        "database_write": False,
                    },
                }

                with snapshots_file.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")) + "\n")
                samples += 1
            except Exception as exc:
                with errors_file.open("a", encoding="utf-8") as stream:
                    stream.write(f"{now_iso()} {type(exc).__name__}: {exc}\n")

            elapsed = time.monotonic() - started
            remaining = max(0.0, INTERVAL_SECONDS - elapsed)
            if remaining:
                time.sleep(remaining)
    finally:
        metadata["stopped_at"] = now_iso()
        metadata["sample_count"] = samples
        metadata["status"] = "completed"
        metadata_file.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        ACTIVE_FILE.unlink(missing_ok=True)
        STOP_FILE.unlink(missing_ok=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
