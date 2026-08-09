#!/usr/bin/env python3

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"

sys.path.insert(0, str(BACKEND))

from app.geocooling.rc1_architecture import architecture_status


def main() -> int:
    status = architecture_status()

    print("============================================================")
    print(" GEOCOOLING RC1 — ARCHITECTURE FREEZE")
    print("============================================================")
    print()

    print("Autorité canonique :")

    for role, value in status["authority"].items():
        print(f" - {role:10s}: {value}")

    print()
    print("Pipeline canonique :")

    for item in status["pipeline"]:
        marker = "OK" if item["available"] else "MISSING"

        print(
            f" [{marker:7s}] "
            f"{item['role']:15s} -> "
            f"{item['module']}"
        )

    print()
    print("Composants legacy / advisory :")

    for item in status["legacy_or_advisory"]:
        marker = "présent" if item["available"] else "absent"

        print(
            f" - {item['role']:28s}: "
            f"{marker}"
        )

    output_dir = REPO / "audits" / "rc1-architecture"
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_file = output_dir / "status.json"

    output_file.write_text(
        json.dumps(
            status,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print("Rapport :", output_file)
    print("Prêt    :", status["ready"])

    if status["missing_required"]:
        print()
        print("Composants requis manquants :")

        for role in status["missing_required"]:
            print(f" - {role}")

        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
