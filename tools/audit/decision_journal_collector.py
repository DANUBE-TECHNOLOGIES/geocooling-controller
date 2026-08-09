#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

REPO = Path(os.getenv(
    "GEOCOOLING_REPO",
    "/opt/stacks/smart-building-controller",
))
DATA_ROOT = REPO / "decision-journal"
ACTIVE = DATA_ROOT / ".active"
STOP = DATA_ROOT / ".stop"

BASE_URL = os.getenv(
    "GEOCOOLING_INTERNAL_API_BASE_URL",
    "http://127.0.0.1:8000",
).rstrip("/")

INTERVAL = max(
    10,
    int(os.getenv("GEOCOOLING_DECISION_JOURNAL_INTERVAL_SECONDS", "30")),
)

running = True


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def handle_signal(signum: int, frame: Any) -> None:
    global running
    running = False


def fetch_json(route: str) -> dict[str, Any]:
    request = Request(
        BASE_URL + route,
        method="GET",
        headers={
            "Accept": "application/json",
            "User-Agent": "GeoCooling-RC17D/1.0",
        },
    )

    with urlopen(request, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))

    if not isinstance(payload, dict):
        raise TypeError("JSON root must be an object")

    return payload


def nested(payload: dict[str, Any], *path: str) -> Any:
    current: Any = payload

    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)

    return current


def append_csv(path: Path, payload: dict[str, Any]) -> None:
    row = {
        "timestamp": payload.get("timestamp"),
        "action": nested(payload, "recommendation", "action"),
        "confidence": nested(payload, "recommendation", "confidence"),
        "blocking": payload.get("blocking"),
        "risk_level": payload.get("highest_risk_level"),
        "indoor_temperature_c": nested(
            payload,
            "measurements",
            "indoor_temperature_c",
        ),
        "outdoor_temperature_c": nested(
            payload,
            "measurements",
            "outdoor_temperature_c",
        ),
        "indoor_humidity_pct": nested(
            payload,
            "measurements",
            "indoor_humidity_pct",
        ),
        "dew_point_c": nested(
            payload,
            "measurements",
            "dew_point_c",
        ),
        "condensation_margin_c": nested(
            payload,
            "configuration",
            "condensation_margin_c",
        ),
        "weather_available": nested(
            payload,
            "availability",
            "weather",
        ),
        "historian_available": nested(
            payload,
            "availability",
            "historian",
        ),
        "learning_available": nested(
            payload,
            "availability",
            "learning",
        ),
        "prediction_available": nested(
            payload,
            "availability",
            "prediction",
        ),
        "hardware_available": nested(
            payload,
            "availability",
            "hardware",
        ),
    }

    write_header = not path.exists()

    with path.open("a", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(row))
        if write_header:
            writer.writeheader()
        writer.writerow(row)


def main() -> int:
    DATA_ROOT.mkdir(parents=True, exist_ok=True)

    session = DATA_ROOT / datetime.now().strftime("session-%Y%m%d-%H%M%S")
    session.mkdir(parents=True, exist_ok=False)

    ACTIVE.write_text(str(session), encoding="utf-8")
    STOP.unlink(missing_ok=True)

    metadata = {
        "schema": "geocooling.rc17d.decision-journal.v1",
        "started_at": utc_now(),
        "interval_seconds": INTERVAL,
        "source": "/geocooling/decision-context/live",
        "http_methods_used": ["GET"],
        "hardware_write": False,
        "mqtt_publish": False,
        "database_write": False,
        "pid": os.getpid(),
    }

    (session / "metadata.json").write_text(
        json.dumps(metadata, indent=2),
        encoding="utf-8",
    )

    jsonl = session / "contexts.jsonl"
    csv_file = session / "summary.csv"
    errors = session / "errors.log"

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    samples = 0

    try:
        while running and not STOP.exists():
            started = time.monotonic()

            try:
                payload = fetch_json(
                    "/geocooling/decision-context/live"
                )

                with jsonl.open("a", encoding="utf-8") as stream:
                    stream.write(
                        json.dumps(
                            payload,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                        + "\n"
                    )

                append_csv(csv_file, payload)
                samples += 1

            except Exception as exc:
                with errors.open("a", encoding="utf-8") as stream:
                    stream.write(
                        f"{utc_now()} {type(exc).__name__}: {exc}\n"
                    )

            elapsed = time.monotonic() - started
            wait = max(0.0, INTERVAL - elapsed)

            if wait:
                time.sleep(wait)

    finally:
        metadata["stopped_at"] = utc_now()
        metadata["sample_count"] = samples
        metadata["status"] = "completed"

        (session / "metadata.json").write_text(
            json.dumps(metadata, indent=2),
            encoding="utf-8",
        )

        ACTIVE.unlink(missing_ok=True)
        STOP.unlink(missing_ok=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
