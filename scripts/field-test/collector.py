#!/usr/bin/env python3

from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def find_first(
    value: Any,
    candidates: tuple[str, ...],
) -> Any:
    candidate_set = {
        candidate.lower()
        for candidate in candidates
    }

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            for key, item in node.items():
                if str(key).lower() in candidate_set:
                    return item

            for item in node.values():
                result = walk(item)

                if result is not None:
                    return result

        elif isinstance(node, list):
            for item in node:
                result = walk(item)

                if result is not None:
                    return result

        return None

    return walk(value)


def number(value: Any) -> float | None:
    try:
        converted = float(value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(converted):
        return None

    return round(converted, 3)


def boolean(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return bool(value)

    if isinstance(value, str):
        normalized = value.strip().lower()

        if normalized in {"true", "on", "yes", "1", "running", "open"}:
            return True

        if normalized in {"false", "off", "no", "0", "stopped", "closed"}:
            return False

    return None


def main() -> int:
    if len(sys.argv) != 3:
        print(
            "usage: collector.py CAMPAIGN_DIRECTORY TIMESTAMP",
            file=sys.stderr,
        )
        return 2

    directory = Path(sys.argv[1])
    timestamp = sys.argv[2]
    data_dir = directory / "data"

    payloads: dict[str, Any] = {}

    for path in sorted(data_dir.glob(f"{timestamp}-*.json")):
        name = path.stem.removeprefix(timestamp + "-")
        payloads[name] = load_json(path)

    dashboard = payloads.get("dashboard")
    thermal = payloads.get("thermal")
    brain = payloads.get("brain")
    prediction = payloads.get("prediction")
    safety = payloads.get("safety")
    relay = payloads.get("relay-status")
    readiness = payloads.get("rc1-readiness")

    merged_sources = [
        dashboard,
        thermal,
        brain,
        prediction,
        safety,
        relay,
    ]

    def first(candidates: tuple[str, ...]) -> Any:
        for source in merged_sources:
            result = find_first(source, candidates)

            if result is not None:
                return result

        return None

    sample = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "collection_id": timestamp,
        "indoor_temperature_c": number(
            first((
                "indoor_temperature",
                "inside_temperature",
                "room_temperature",
                "temperature_indoor",
            ))
        ),
        "indoor_humidity_pct": number(
            first((
                "indoor_humidity",
                "inside_humidity",
                "relative_humidity",
                "humidity",
            ))
        ),
        "dew_point_c": number(
            first((
                "dew_point",
                "dew_point_c",
                "point_de_rosee",
            ))
        ),
        "source_in_c": number(
            first((
                "source_in",
                "source_inlet_temperature",
                "source_input_temperature",
            ))
        ),
        "source_out_c": number(
            first((
                "source_out",
                "source_outlet_temperature",
                "source_output_temperature",
            ))
        ),
        "floor_supply_c": number(
            first((
                "floor_supply",
                "supply_temperature",
                "departure_temperature",
                "depart_temperature",
            ))
        ),
        "floor_return_c": number(
            first((
                "floor_return",
                "return_temperature",
                "retour_temperature",
            ))
        ),
        "flow_l_min": number(
            first((
                "flow_l_min",
                "flow_rate",
                "flow",
            ))
        ),
        "cooling_power_kw": number(
            first((
                "cooling_power_kw",
                "thermal_power_kw",
                "power_kw",
            ))
        ),
        "condensation_margin_c": number(
            first((
                "condensation_margin",
                "condensation_margin_c",
                "dew_point_margin",
            ))
        ),
        "pump_running": boolean(
            first((
                "pump_running",
                "pump",
                "circulator_running",
            ))
        ),
        "valve_open": boolean(
            first((
                "valve_open",
                "valve",
            ))
        ),
        "brain_decision": first((
            "decision",
            "brain_decision",
            "recommended_action",
            "action",
        )),
        "brain_confidence": number(
            first((
                "confidence",
                "brain_confidence",
                "prediction_confidence",
            ))
        ),
        "predicted_temperature_c": number(
            find_first(
                prediction,
                (
                    "predicted_temperature",
                    "temperature_prediction",
                    "predicted_indoor_temperature",
                ),
            )
        ),
        "safety_ok": boolean(
            find_first(
                safety,
                (
                    "safe",
                    "safety_ok",
                    "allowed",
                    "ready",
                ),
            )
        ),
        "rc1_ready": boolean(
            find_first(
                readiness,
                ("ready",),
            )
        ),
        "available_payloads": sorted(
            key
            for key, value in payloads.items()
            if value is not None
        ),
    }

    samples_file = directory / "samples.jsonl"

    with samples_file.open("a", encoding="utf-8") as stream:
        stream.write(
            json.dumps(
                sample,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            + "\n"
        )

    csv_file = directory / "samples.csv"

    columns = [
        "timestamp",
        "collection_id",
        "indoor_temperature_c",
        "indoor_humidity_pct",
        "dew_point_c",
        "source_in_c",
        "source_out_c",
        "floor_supply_c",
        "floor_return_c",
        "flow_l_min",
        "cooling_power_kw",
        "condensation_margin_c",
        "pump_running",
        "valve_open",
        "brain_decision",
        "brain_confidence",
        "predicted_temperature_c",
        "safety_ok",
        "rc1_ready",
    ]

    if not csv_file.exists():
        csv_file.write_text(
            ",".join(columns) + "\n",
            encoding="utf-8",
        )

    def csv_value(value: Any) -> str:
        if value is None:
            return ""

        text = str(value)

        if any(character in text for character in {",", '"', "\n"}):
            text = '"' + text.replace('"', '""') + '"'

        return text

    with csv_file.open("a", encoding="utf-8") as stream:
        stream.write(
            ",".join(
                csv_value(sample.get(column))
                for column in columns
            )
            + "\n"
        )

    print(json.dumps(sample, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
