from __future__ import annotations
from pathlib import Path
from typing import Any, Mapping

from app.geocooling.rc3.predictor_calibration import (
    CalibrationSample,
    PredictorCalibrationEngine,
)
from app.geocooling.rc3.prediction_validation import (
    PredictionValidationEngine,
    load_latest_session,
)
from app.geocooling.rc3.weather_inertia_live import (
    LiveWeatherInertiaPredictionService,
)


class ValidationCalibrationBridge:
    def __init__(
        self,
        repo_root: Path | None = None,
        validation_engine: PredictionValidationEngine | None = None,
        calibration_engine: PredictorCalibrationEngine | None = None,
        prediction_service: LiveWeatherInertiaPredictionService | None = None,
    ) -> None:
        self.repo_root = repo_root or Path(
            "/opt/stacks/smart-building-controller"
        )
        self.validation_engine = (
            validation_engine or PredictionValidationEngine()
        )
        self.calibration_engine = (
            calibration_engine or PredictorCalibrationEngine()
        )
        self.prediction_service = (
            prediction_service
            or LiveWeatherInertiaPredictionService()
        )

    @staticmethod
    def sample_from_match(
        match: Mapping[str, Any],
    ) -> CalibrationSample | None:
        try:
            horizon = int(match["horizon_minutes"])
            predicted = float(
                match["predicted_indoor_temperature_c"]
            )
            actual = float(
                match["actual_indoor_temperature_c"]
            )
        except (KeyError, TypeError, ValueError):
            return None

        return CalibrationSample(
            horizon_minutes=horizon,
            predicted_c=predicted,
            actual_c=actual,
            error_c=predicted - actual,
        )

    def build(self) -> dict[str, Any]:
        journal_root = (
            self.repo_root / "rc3-prediction-journal"
        )
        snapshots = load_latest_session(journal_root)
        validation = self.validation_engine.validate(
            snapshots
        )

        samples = tuple(
            sample
            for sample in (
                self.sample_from_match(match)
                for match in validation.get("matches", [])
                if isinstance(match, Mapping)
            )
            if sample is not None
        )

        prediction = self.prediction_service.predict()
        current_model = prediction.get("model", {})

        calibration = self.calibration_engine.calibrate(
            current_model=current_model,
            samples=samples,
        )

        return {
            "schema": (
                "geocooling.rc38."
                "validation-calibration-bridge.v1"
            ),
            "status": {
                "prediction_snapshots": len(snapshots),
                "validation_matches": int(
                    validation.get("match_count") or 0
                ),
                "calibration_samples": len(samples),
                "validation_ready": bool(
                    validation.get(
                        "readiness",
                        {},
                    ).get("enough_data")
                ),
                "calibration_ready": (
                    calibration.get("status")
                    == "PROPOSAL_READY"
                ),
            },
            "validation": {
                "metrics": validation.get("metrics", {}),
                "by_horizon": validation.get(
                    "by_horizon",
                    {},
                ),
                "readiness": validation.get(
                    "readiness",
                    {},
                ),
            },
            "calibration": calibration,
            "active_model": current_model,
            "activation": {
                "automatic": False,
                "requires_review": True,
                "controller_authorized": False,
                "hardware_called": False,
            },
            "safety": {
                "analysis_only": True,
                "hardware_write": False,
                "mqtt_publish": False,
                "database_write": False,
            },
        }
