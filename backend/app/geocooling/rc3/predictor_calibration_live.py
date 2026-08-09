"""
RC3.6 live calibration proposal service.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.geocooling.rc3.predictor_calibration import (
    PredictorCalibrationEngine,
    collect_samples_from_journals,
)
from app.geocooling.rc3.weather_inertia_live import (
    LiveWeatherInertiaPredictionService,
)


class LivePredictorCalibrationService:
    def __init__(
        self,
        *,
        prediction_service: LiveWeatherInertiaPredictionService | None = None,
        engine: PredictorCalibrationEngine | None = None,
        repo_root: Path | None = None,
    ) -> None:
        self.prediction_service = (
            prediction_service
            or LiveWeatherInertiaPredictionService()
        )
        self.engine = engine or PredictorCalibrationEngine()
        self.repo_root = repo_root or Path(
            "/opt/stacks/smart-building-controller"
        )

    def propose(self) -> dict[str, Any]:
        prediction = self.prediction_service.predict()
        current_model = prediction.get("model", {})

        samples = collect_samples_from_journals(
            (
                self.repo_root / "decision-journal",
                self.repo_root / "scenario-journal",
                self.repo_root / "rc3-shadow-journal",
                self.repo_root / "audits",
            )
        )

        report = self.engine.calibrate(
            current_model=current_model,
            samples=samples,
        )
        report["sources"] = {
            "journal_roots": [
                "decision-journal",
                "scenario-journal",
                "rc3-shadow-journal",
                "audits",
            ],
            "prediction_schema": prediction.get("schema"),
        }

        return report
