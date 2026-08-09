"""
RC3.7 live validation service.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.geocooling.rc3.prediction_validation import (
    PredictionValidationEngine,
    load_latest_session,
)


class LivePredictionValidationService:
    def __init__(
        self,
        *,
        root: Path | None = None,
        engine: PredictionValidationEngine | None = None,
    ) -> None:
        self.root = root or Path(
            "/opt/stacks/smart-building-controller/"
            "rc3-prediction-journal"
        )
        self.engine = (
            engine
            or PredictionValidationEngine()
        )

    def report(self) -> dict[str, Any]:
        snapshots = load_latest_session(self.root)
        report = self.engine.validate(snapshots)
        report["journal_root"] = str(self.root)
        return report
