#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import os
import signal
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

REPO = Path(
    os.getenv(
        "GEOCOOLING_REPO",
        "/opt/stacks/smart-building-controller",
    )
)
DATA_ROOT = REPO / "scenario-journal"
ACTIVE_FILE = DATA_ROOT / ".active-session"
STOP_FILE = DATA_ROOT / ".stop"

BASE_URL = os.getenv(
    "GEOCOOLING_INTERNAL_API_BASE_URL",
    "http://127.0.0.1:8000",
).rstrip("/")

INTERVAL_SECONDS = max(
    10,
    int(
        os.getenv(
            "GEOCOOLING_SCENARIO_JOURNAL_INTERVAL_SECONDS",
            "30",
        )
    ),
)

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
        headers={
            "Accept": "application/json",
            "User-Agent": "GeoCooling-RC21C/1.0",
        },
    )

    with urlopen(request, timeout=15) as response:
        payload = json.loads(
            response.read().decode("utf-8")
        )

    if not isinstance(payload, dict):
        raise TypeError("JSON root must be an object")

    return payload


def nested(
    payload: dict[str, Any],
    *path: str,
) -> Any:
    current: Any = payload

    for key in path:
        if not isinstance(current, dict):
            return None

        current = current.get(key)

    return current


def append_csv(
    csv_path: Path,
    payload: dict[str, Any],
) -> None:
    selected = nested(
        payload,
        "scenario_decision",
        "selected",
    )

    if not isinstance(selected, dict):
        selected = {}

    row = {
        "generated_at": payload.get("generated_at"),
        "selected_scenario": selected.get("scenario"),
        "selected_score": selected.get("score"),
        "comfort_score": selected.get("comfort_score"),
        "safety_score": selected.get("safety_score"),
        "energy_score": selected.get("energy_score"),
        "stability_score": selected.get("stability_score"),
        "learning_score": selected.get("learning_score"),
        "predicted_indoor_temperature_c": selected.get(
            "predicted_indoor_temperature_c"
        ),
        "estimated_runtime_minutes": selected.get(
            "estimated_runtime_minutes"
        ),
        "estimated_energy_kwh": selected.get(
            "estimated_energy_kwh"
        ),
        "condensation_risk": selected.get(
            "condensation_risk"
        ),
        "decision_confidence": nested(
            payload,
            "scenario_decision",
            "confidence",
        ),
        "context_action": nested(
            payload,
            "context",
            "recommendation",
            "action",
        ),
        "context_confidence": nested(
            payload,
            "context",
            "recommendation",
            "confidence",
        ),
        "blocking": nested(
            payload,
            "context",
            "blocking",
        ),
        "highest_risk_level": nested(
            payload,
            "context",
            "highest_risk_level",
        ),
        "indoor_temperature_c": nested(
            payload,
            "context",
            "measurements",
            "indoor_temperature_c",
        ),
        "outdoor_temperature_c": nested(
            payload,
            "context",
            "measurements",
            "outdoor_temperature_c",
        ),
        "condensation_margin_c": nested(
            payload,
            "context",
            "configuration",
            "condensation_margin_c",
        ),
    }

    write_header = not csv_path.exists()

    with csv_path.open(
        "a",
        newline="",
        encoding="utf-8",
    ) as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=list(row),
        )

        if write_header:
            writer.writeheader()

        writer.writerow(row)


def main() -> int:
    DATA_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    session = DATA_ROOT / datetime.now().strftime(
        "session-%Y%m%d-%H%M%S"
    )
    session.mkdir(
        parents=True,
        exist_ok=False,
    )

    ACTIVE_FILE.write_text(
        str(session),
        encoding="utf-8",
    )
    STOP_FILE.unlink(
        missing_ok=True,
    )

    metadata = {
        "schema": "geocooling.rc21c.scenario-journal.v1",
        "started_at": now_iso(),
        "interval_seconds": INTERVAL_SECONDS,
        "source_route": "/geocooling/scenario-engine/live",
        "read_only": True,
        "http_methods_used": ["GET"],
        "hardware_write": False,
        "mqtt_publish": False,
        "database_write": False,
        "pid": os.getpid(),
    }

    metadata_file = session / "metadata.json"
    metadata_file.write_text(
        json.dumps(
            metadata,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    journal_file = session / "scenario-decisions.jsonl"
    csv_file = session / "summary.csv"
    errors_file = session / "errors.log"

    signal.signal(
        signal.SIGTERM,
        stop_handler,
    )
    signal.signal(
        signal.SIGINT,
        stop_handler,
    )

    samples = 0

    try:
        while running and not STOP_FILE.exists():
            started = time.monotonic()

            try:
                payload = get_json(
                    "/geocooling/scenario-engine/live"
                )

                with journal_file.open(
                    "a",
                    encoding="utf-8",
                ) as stream:
                    stream.write(
                        json.dumps(
                            payload,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                        + "\n"
                    )

                append_csv(
                    csv_file,
                    payload,
                )
                samples += 1

            except Exception as exc:
                with errors_file.open(
                    "a",
                    encoding="utf-8",
                ) as stream:
                    stream.write(
                        f"{now_iso()} "
                        f"{type(exc).__name__}: {exc}\n"
                    )

            elapsed = time.monotonic() - started
            remaining = max(
                0.0,
                INTERVAL_SECONDS - elapsed,
            )

            if remaining:
                time.sleep(remaining)

    finally:
        metadata["stopped_at"] = now_iso()
        metadata["sample_count"] = samples
        metadata["status"] = "completed"

        metadata_file.write_text(
            json.dumps(
                metadata,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        ACTIVE_FILE.unlink(
            missing_ok=True,
        )
        STOP_FILE.unlink(
            missing_ok=True,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
