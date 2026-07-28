"""C023.2 — Calibration consultative du jumeau numérique GeoCooling.

Ce module ne commande aucun équipement. Il relie le Digital Twin existant,
le modèle adaptatif et les prévisions C023.1 afin de mesurer la précision
réelle du modèle thermique dans le temps.
"""
from __future__ import annotations

import json
import math
import os
import threading
import uuid
from collections import deque
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_iso(value: datetime | None = None) -> str:
    return (value or utc_now()).astimezone(timezone.utc).isoformat()


def finite(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


class DigitalTwinCalibration:
    VERSION = "C023.2"
    HORIZONS = (30, 60, 120, 240)

    def __init__(self, *, controller: Any, digital_twin: Any, forecast_engine: Any) -> None:
        self.controller = controller
        self.digital_twin = digital_twin
        self.forecast_engine = forecast_engine
        self._lock = threading.RLock()
        self._capacity = max(20, int(os.getenv("GEOCOOLING_TWIN_CALIBRATION_CAPACITY", "500")))
        self._records: deque[dict[str, Any]] = deque(maxlen=self._capacity)
        self._pending: deque[dict[str, Any]] = deque(maxlen=self._capacity)
        data_dir = Path(os.getenv("GEOCOOLING_DATA_DIR", "/app/data/geocooling"))
        self._path = Path(os.getenv("GEOCOOLING_TWIN_CALIBRATION_FILE", str(data_dir / "digital-twin-calibration.jsonl")))
        self._last_error: str | None = None
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            for raw in self._path.read_text(encoding="utf-8").splitlines()[-self._capacity:]:
                try:
                    item = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    continue
                if item.get("type") == "observation":
                    self._records.append(item)
                elif item.get("type") == "pending":
                    self._pending.append(item)
        except OSError as exc:
            self._last_error = str(exc)

    def _append(self, item: dict[str, Any]) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")
            self._last_error = None
        except OSError as exc:
            self._last_error = str(exc)

    @staticmethod
    def _indoor_from_snapshot(snapshot: dict[str, Any]) -> float | None:
        installation = snapshot.get("installation", {}) if isinstance(snapshot, dict) else {}
        building = installation.get("building", {}) if isinstance(installation, dict) else {}
        return finite(building.get("indoor_c"))

    def _adaptive(self) -> dict[str, Any]:
        brain = getattr(self.controller, "brain", None)
        model = getattr(brain, "adaptive_model", None)
        estimate = getattr(model, "estimate", None)
        if not callable(estimate):
            return {"available": False, "reason": "Modèle adaptatif indisponible"}
        try:
            value = estimate()
            as_dict = getattr(value, "as_dict", None)
            return as_dict() if callable(as_dict) else dict(value)
        except Exception as exc:
            return {"available": False, "reason": f"Lecture impossible: {exc}"}

    def capture(self) -> dict[str, Any]:
        """Capture la meilleure prévision actuelle pour évaluation future."""
        payload = self.forecast_engine.forecast()
        forecast = payload.get("forecast", {})
        now = utc_now()
        capture_id = str(uuid.uuid4())
        created: list[dict[str, Any]] = []
        with self._lock:
            for horizon in self.HORIZONS:
                point = forecast.get(f"{horizon}m", {})
                predicted = finite(point.get("indoor_temperature_c"))
                if predicted is None:
                    continue
                item = {
                    "type": "pending",
                    "capture_id": capture_id,
                    "created_at": utc_iso(now),
                    "due_at": utc_iso(now + timedelta(minutes=horizon)),
                    "horizon_minutes": horizon,
                    "strategy": payload.get("recommended_strategy"),
                    "predicted_temperature_c": predicted,
                    "model": payload.get("model"),
                }
                self._pending.append(item)
                self._append(item)
                created.append(deepcopy(item))
        return {
            "capture_id": capture_id,
            "created_at": utc_iso(now),
            "read_only": True,
            "pending_predictions": created,
            "count": len(created),
        }

    def observe(self, *, predicted_temperature_c: float, observed_temperature_c: float,
                horizon_minutes: int, strategy: str | None = None,
                capture_id: str | None = None, source: str = "manual") -> dict[str, Any]:
        predicted = finite(predicted_temperature_c)
        observed = finite(observed_temperature_c)
        if predicted is None or observed is None:
            raise ValueError("Températures prédites et observées obligatoires")
        error = observed - predicted
        item = {
            "type": "observation",
            "observation_id": str(uuid.uuid4()),
            "capture_id": capture_id,
            "observed_at": utc_iso(),
            "horizon_minutes": int(horizon_minutes),
            "strategy": strategy,
            "predicted_temperature_c": round(predicted, 3),
            "observed_temperature_c": round(observed, 3),
            "error_c": round(error, 3),
            "absolute_error_c": round(abs(error), 3),
            "source": source,
        }
        with self._lock:
            self._records.append(item)
            self._append(item)
        return deepcopy(item)

    def evaluate_due(self) -> dict[str, Any]:
        """Évalue les prévisions arrivées à échéance avec la mesure intérieure actuelle."""
        snapshot = self.digital_twin.snapshot(refresh=True)
        observed = self._indoor_from_snapshot(snapshot)
        if observed is None:
            return {"evaluated": 0, "remaining": len(self._pending), "reason": "Température intérieure indisponible"}
        now = utc_now()
        evaluated = 0
        remaining: deque[dict[str, Any]] = deque(maxlen=self._capacity)
        with self._lock:
            while self._pending:
                item = self._pending.popleft()
                try:
                    due = datetime.fromisoformat(str(item["due_at"]))
                    if due.tzinfo is None:
                        due = due.replace(tzinfo=timezone.utc)
                except Exception:
                    continue
                if due <= now:
                    self.observe(
                        predicted_temperature_c=item["predicted_temperature_c"],
                        observed_temperature_c=observed,
                        horizon_minutes=item["horizon_minutes"],
                        strategy=item.get("strategy"),
                        capture_id=item.get("capture_id"),
                        source="automatic_due_evaluation",
                    )
                    evaluated += 1
                else:
                    remaining.append(item)
            self._pending = remaining
        return {"evaluated": evaluated, "remaining": len(self._pending), "observed_temperature_c": observed}

    def _metrics(self) -> dict[str, Any]:
        rows = list(self._records)
        errors = [finite(row.get("absolute_error_c")) for row in rows]
        errors = [value for value in errors if value is not None]
        signed = [finite(row.get("error_c")) for row in rows]
        signed = [value for value in signed if value is not None]
        by_horizon: dict[str, dict[str, Any]] = {}
        for horizon in self.HORIZONS:
            values = [finite(row.get("absolute_error_c")) for row in rows if int(row.get("horizon_minutes", 0)) == horizon]
            values = [value for value in values if value is not None]
            by_horizon[f"{horizon}m"] = {
                "samples": len(values),
                "mean_absolute_error_c": round(sum(values) / len(values), 3) if values else None,
                "maximum_absolute_error_c": round(max(values), 3) if values else None,
            }
        mae = sum(errors) / len(errors) if errors else None
        max_error = max(errors) if errors else None
        bias = sum(signed) / len(signed) if signed else None
        if not errors:
            quality = "UNASSESSED"
        elif len(errors) < 5:
            quality = "LEARNING"
        elif mae is not None and mae <= 0.25:
            quality = "EXCELLENT"
        elif mae is not None and mae <= 0.50:
            quality = "GOOD"
        elif mae is not None and mae <= 1.00:
            quality = "FAIR"
        else:
            quality = "POOR"
        accuracy = None if mae is None else max(0, min(100, round(100 - mae * 40)))
        return {
            "sample_count": len(errors),
            "mean_absolute_error_c": round(mae, 3) if mae is not None else None,
            "maximum_absolute_error_c": round(max_error, 3) if max_error is not None else None,
            "mean_bias_c": round(bias, 3) if bias is not None else None,
            "accuracy_index": accuracy,
            "quality": quality,
            "by_horizon": by_horizon,
        }

    def status(self, *, evaluate_due: bool = True) -> dict[str, Any]:
        evaluation = self.evaluate_due() if evaluate_due else {"evaluated": 0, "remaining": len(self._pending)}
        adaptive = self._adaptive()
        metrics = self._metrics()
        adaptive_confidence = int(adaptive.get("confidence", 0) or 0)
        sample_score = min(40, metrics["sample_count"] * 4)
        calibration_level = min(100, round(adaptive_confidence * 0.6 + sample_score))
        if calibration_level < 20:
            phase = "INITIAL"
            recommendation = "Collecter des mesures thermiques et plusieurs cycles réels."
        elif calibration_level < 60:
            phase = "LEARNING"
            recommendation = "Poursuivre l'observation ; ne pas automatiser les paramètres du modèle."
        elif metrics["quality"] in {"POOR", "FAIR"}:
            phase = "REVIEW_REQUIRED"
            recommendation = "Vérifier les paramètres d'inertie, de puissance et les sondes."
        else:
            phase = "CALIBRATED"
            recommendation = "Modèle exploitable pour l'aide à la décision, toujours en lecture seule."
        return {
            "component": "digital_twin_calibration",
            "version": self.VERSION,
            "read_only": True,
            "calibration_level_percent": calibration_level,
            "phase": phase,
            "recommendation": recommendation,
            "adaptive_model": adaptive,
            "prediction_accuracy": metrics,
            "pending_predictions": len(self._pending),
            "last_observation": deepcopy(self._records[-1]) if self._records else None,
            "due_evaluation": evaluation,
            "storage": {"path": str(self._path), "last_error": self._last_error},
        }

    def model(self) -> dict[str, Any]:
        return {
            "generated_at": utc_iso(),
            "read_only": True,
            "digital_twin": self.digital_twin.snapshot(refresh=True),
            "forecast": self.forecast_engine.forecast(),
            "calibration": self.status(evaluate_due=True),
        }

    def history(self, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), self._capacity))
        with self._lock:
            return deepcopy(list(self._records)[-limit:])
