from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


class GeoCoolingThermalModelValidation:
    """Cross-validates learned parameters before an advisory-only promotion."""

    VERSION = "H019-MODEL-VALIDATION-1.0"

    def __init__(self, model: Any, learner: Any, path: str | None = None) -> None:
        self.model = model
        self.learner = learner
        base = Path(os.getenv("GEOCOOLING_DATA_DIR", "/app/data/geocooling"))
        self.path = Path(path or os.getenv("GEOCOOLING_MODEL_VALIDATION_PATH", str(base / "thermal-model-validation.json")))
        self.minimum_scenarios = int(os.getenv("GEOCOOLING_MODEL_VALIDATION_MIN_SCENARIOS", "6"))
        self.minimum_improvement_percent = float(os.getenv("GEOCOOLING_MODEL_VALIDATION_MIN_IMPROVEMENT_PERCENT", "5"))
        self.promoted_adjustments = {"heat_capacity_factor": 1.0, "cooling_power_factor": 1.0}
        self.previous_adjustments: dict[str, float] | None = None
        self.last_evaluation: dict[str, Any] | None = None
        self.history: list[dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            promoted = data.get("promoted_adjustments")
            previous = data.get("previous_adjustments")
            if isinstance(promoted, dict):
                self.promoted_adjustments.update(promoted)
            if isinstance(previous, dict):
                self.previous_adjustments = {key: float(value) for key, value in previous.items()}
            if isinstance(data.get("last_evaluation"), dict):
                self.last_evaluation = data["last_evaluation"]
            if isinstance(data.get("history"), list):
                self.history = data["history"][-100:]
        except Exception:
            return

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(self.path.suffix + ".tmp")
            temporary.write_text(json.dumps({
                "promoted_adjustments": self.promoted_adjustments,
                "previous_adjustments": self.previous_adjustments,
                "last_evaluation": self.last_evaluation,
                "history": self.history[-100:],
            }, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(self.path)
        except Exception:
            pass

    @staticmethod
    def _metric(errors: list[float]) -> dict[str, Any]:
        if not errors:
            return {"count": 0, "mae_c": None, "rmse_c": None, "max_error_c": None}
        return {
            "count": len(errors),
            "mae_c": round(sum(abs(value) for value in errors) / len(errors), 4),
            "rmse_c": round(math.sqrt(sum(value * value for value in errors) / len(errors)), 4),
            "max_error_c": round(max(abs(value) for value in errors), 4),
        }

    def _predict_with(self, payload: dict[str, Any], adjustments: dict[str, float]) -> float:
        original_capacity = self.model.heat_capacity_kwh_per_c
        original_power = self.model.nominal_cooling_kw
        try:
            self.model.heat_capacity_kwh_per_c = original_capacity * float(adjustments["heat_capacity_factor"])
            self.model.nominal_cooling_kw = original_power * float(adjustments["cooling_power_factor"])
            result = self.model.predict(payload)
        finally:
            self.model.heat_capacity_kwh_per_c = original_capacity
            self.model.nominal_cooling_kw = original_power
        predicted = finite(result.get("prediction", {}).get("final_temperature_c"))
        if predicted is None:
            raise ValueError("model did not return a final temperature")
        return predicted

    def status(self) -> dict[str, Any]:
        return {
            "generated_at": utc_now_iso(),
            "version": self.VERSION,
            "advisory_only": True,
            "physical_activation_allowed": False,
            "hardware_touched": False,
            "candidate_adjustments": dict(self.learner.adjustments),
            "promoted_adjustments": dict(self.promoted_adjustments),
            "previous_adjustments": self.previous_adjustments,
            "last_evaluation": self.last_evaluation,
            "promotion_policy": {
                "minimum_scenarios": self.minimum_scenarios,
                "minimum_validation_improvement_percent": self.minimum_improvement_percent,
                "maximum_error_regression_allowed": False,
            },
        }

    def evaluate(self, payload: dict[str, Any]) -> dict[str, Any]:
        scenarios = payload.get("scenarios")
        if not isinstance(scenarios, list) or len(scenarios) < self.minimum_scenarios:
            raise ValueError(f"at least {self.minimum_scenarios} scenarios are required")

        baseline_errors: list[float] = []
        candidate_errors: list[float] = []
        rows: list[dict[str, Any]] = []
        candidate = {key: float(value) for key, value in self.learner.adjustments.items()}
        baseline = dict(self.promoted_adjustments)

        for index, scenario in enumerate(scenarios):
            if not isinstance(scenario, dict):
                raise ValueError(f"scenario {index} must be an object")
            observed = finite(scenario.get("observed_temperature_c"))
            if observed is None:
                raise ValueError(f"scenario {index} requires observed_temperature_c")
            model_payload = {key: value for key, value in scenario.items() if key != "observed_temperature_c"}
            baseline_prediction = self._predict_with(model_payload, baseline)
            candidate_prediction = self._predict_with(model_payload, candidate)
            baseline_error = observed - baseline_prediction
            candidate_error = observed - candidate_prediction
            baseline_errors.append(baseline_error)
            candidate_errors.append(candidate_error)
            rows.append({
                "index": index,
                "observed_temperature_c": observed,
                "baseline_prediction_c": round(baseline_prediction, 4),
                "candidate_prediction_c": round(candidate_prediction, 4),
                "baseline_error_c": round(baseline_error, 4),
                "candidate_error_c": round(candidate_error, 4),
            })

        split = max(1, int(len(rows) * 0.7))
        if split >= len(rows):
            split = len(rows) - 1
        train_base = self._metric(baseline_errors[:split])
        train_candidate = self._metric(candidate_errors[:split])
        validation_base = self._metric(baseline_errors[split:])
        validation_candidate = self._metric(candidate_errors[split:])
        base_mae = float(validation_base["mae_c"])
        candidate_mae = float(validation_candidate["mae_c"])
        improvement = 0.0 if base_mae == 0 else ((base_mae - candidate_mae) / base_mae) * 100.0
        max_error_safe = float(validation_candidate["max_error_c"]) <= float(validation_base["max_error_c"])
        train_improved = float(train_candidate["mae_c"]) <= float(train_base["mae_c"])
        validation_improved = improvement >= self.minimum_improvement_percent
        overfit_detected = train_improved and candidate_mae > base_mae
        promotable = validation_improved and max_error_safe and not overfit_detected

        evaluation = {
            "evaluated_at": utc_now_iso(),
            "scenario_count": len(rows),
            "split": {"training": split, "validation": len(rows) - split},
            "baseline_adjustments": baseline,
            "candidate_adjustments": candidate,
            "training": {"baseline": train_base, "candidate": train_candidate},
            "validation": {"baseline": validation_base, "candidate": validation_candidate},
            "validation_improvement_percent": round(improvement, 3),
            "overfit_detected": overfit_detected,
            "maximum_error_safe": max_error_safe,
            "promotable": promotable,
            "decision": "PROMOTION_ALLOWED" if promotable else "REJECTED",
            "rows": rows,
            "physical_activation_allowed": False,
            "hardware_touched": False,
        }
        self.last_evaluation = evaluation
        self.history.append({key: value for key, value in evaluation.items() if key != "rows"})
        self._save()
        return evaluation

    def promote(self) -> dict[str, Any]:
        if not self.last_evaluation or not self.last_evaluation.get("promotable"):
            raise ValueError("no promotable evaluation is available")
        self.previous_adjustments = dict(self.promoted_adjustments)
        self.promoted_adjustments = {
            key: float(value) for key, value in self.last_evaluation["candidate_adjustments"].items()
        }
        event = {"promoted_at": utc_now_iso(), "adjustments": dict(self.promoted_adjustments), "physical_activation_allowed": False}
        self.history.append({"event": "PROMOTED", **event})
        self._save()
        return {"promoted": True, **event, "hardware_touched": False}

    def rollback(self) -> dict[str, Any]:
        if self.previous_adjustments is None:
            raise ValueError("no previous promoted adjustments are available")
        current = dict(self.promoted_adjustments)
        self.promoted_adjustments = dict(self.previous_adjustments)
        self.previous_adjustments = current
        self.history.append({"event": "ROLLBACK", "rolled_back_at": utc_now_iso(), "adjustments": dict(self.promoted_adjustments)})
        self._save()
        return {"rolled_back": True, "promoted_adjustments": dict(self.promoted_adjustments), "physical_activation_allowed": False, "hardware_touched": False}

    def predict(self, payload: dict[str, Any]) -> dict[str, Any]:
        predicted = self._predict_with(payload, self.promoted_adjustments)
        return {
            "generated_at": utc_now_iso(),
            "prediction": {"final_temperature_c": round(predicted, 4)},
            "adjustments": dict(self.promoted_adjustments),
            "advisory_only": True,
            "physical_activation_allowed": False,
            "hardware_touched": False,
        }
