"""C023.3 — GeoCooling Efficiency Index (GEI).

Calcul consultatif et strictement en lecture seule. Le score synthétise la
qualité des mesures, le confort, le transfert thermique, l'hydraulique et la
fiabilité du modèle numérique sans jamais piloter un actionneur.
"""
from __future__ import annotations

import json
import math
import os
import threading
from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


class GeoCoolingEfficiencyIndex:
    VERSION = "C023.3"

    def __init__(self, *, controller: Any, digital_twin: Any, calibration: Any) -> None:
        self.controller = controller
        self.digital_twin = digital_twin
        self.calibration = calibration
        self._lock = threading.RLock()
        self._capacity = max(20, int(os.getenv("GEOCOOLING_GEI_HISTORY_CAPACITY", "500")))
        self._history: deque[dict[str, Any]] = deque(maxlen=self._capacity)
        data_dir = Path(os.getenv("GEOCOOLING_DATA_DIR", "/app/data/geocooling"))
        self._path = Path(os.getenv("GEOCOOLING_GEI_FILE", str(data_dir / "efficiency-index.jsonl")))
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
                if isinstance(item, dict) and item.get("component") == "geocooling_efficiency_index":
                    self._history.append(item)
        except OSError as exc:
            self._last_error = str(exc)

    def _persist(self, item: dict[str, Any]) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")
            self._last_error = None
        except OSError as exc:
            self._last_error = str(exc)

    @staticmethod
    def _grade(score: int) -> str:
        if score >= 90:
            return "EXCELLENT"
        if score >= 75:
            return "GOOD"
        if score >= 55:
            return "FAIR"
        if score >= 35:
            return "POOR"
        return "INSUFFICIENT_DATA"

    @staticmethod
    def _nested(data: dict[str, Any], *keys: str) -> Any:
        current: Any = data
        for key in keys:
            if not isinstance(current, dict):
                return None
            current = current.get(key)
        return current

    def _comfort_score(self, indoor: float | None) -> tuple[float, str]:
        target = _number(os.getenv("GEOCOOLING_COMFORT_TARGET_C", "24.0")) or 24.0
        if indoor is None:
            return 0.0, "Température intérieure indisponible"
        deviation = abs(indoor - target)
        score = _clamp(100.0 - deviation * 22.0)
        return score, f"Écart confort {deviation:.2f} °C autour de {target:.1f} °C"

    @staticmethod
    def _hydraulic_score(flow: float | None, pump_on: bool) -> tuple[float, str]:
        if not pump_on:
            return 100.0, "Circulateur arrêté : débit non exigé"
        if flow is None:
            return 0.0, "Circulateur actif mais débit indisponible"
        target = 28.0
        deviation = abs(flow - target)
        score = _clamp(100.0 - deviation * 5.0)
        return score, f"Débit {flow:.1f} l/min, cible indicative {target:.0f} l/min"

    @staticmethod
    def _thermal_score(power_w: float | None, delta_t: float | None, pump_on: bool) -> tuple[float, str]:
        if not pump_on:
            return 100.0, "Aucun transfert thermique attendu à l'arrêt"
        if power_w is not None:
            score = _clamp(power_w / 5000.0 * 100.0)
            return score, f"Puissance frigorifique mesurée {power_w/1000.0:.2f} kW"
        if delta_t is not None:
            score = _clamp(abs(delta_t) / 3.0 * 100.0)
            return score, f"Écart thermique source {abs(delta_t):.2f} °C"
        return 0.0, "Puissance et écart thermique indisponibles"

    @staticmethod
    def _model_score(calibration_status: dict[str, Any]) -> tuple[float, str]:
        accuracy = _number(calibration_status.get("prediction_accuracy", {}).get("accuracy_index"))
        level = _number(calibration_status.get("calibration_level_percent"))
        values = [v for v in (accuracy, level) if v is not None]
        if not values:
            return 0.0, "Modèle non encore calibré"
        score = sum(values) / len(values)
        return _clamp(score), f"Calibration {int(level or 0)} %, précision {int(accuracy or 0)} %"

    @staticmethod
    def _measurement_score(snapshot: dict[str, Any]) -> tuple[float, str]:
        quality = snapshot.get("quality", {}) if isinstance(snapshot, dict) else {}
        available = int(quality.get("available_measurements", 0) or 0)
        missing = quality.get("missing_measurements", []) or []
        total = available + len(missing)
        if total <= 0:
            return 0.0, "Aucune mesure exploitable"
        score = available / total * 100.0
        return score, f"{available}/{total} mesures disponibles"

    def calculate(self, *, persist: bool = True) -> dict[str, Any]:
        snapshot = self.digital_twin.snapshot(refresh=True)
        calibration_status = self.calibration.status(evaluate_due=True)
        installation = snapshot.get("installation", {})
        building = installation.get("building", {})
        hydraulic = installation.get("hydraulic_loop", {})
        thermal = installation.get("thermal_loop", {})

        indoor = _number(building.get("indoor_c"))
        flow = _number(hydraulic.get("flow_l_min"))
        power_w = _number(thermal.get("power_w"))
        delta_t = _number(thermal.get("delta_t_c"))
        pump_state = str(self._nested(hydraulic, "pump", "state") or "OFF").upper()
        pump_on = pump_state in {"ON", "RUNNING", "TRUE", "1"}

        components = {
            "comfort": self._comfort_score(indoor),
            "hydraulic": self._hydraulic_score(flow, pump_on),
            "thermal_transfer": self._thermal_score(power_w, delta_t, pump_on),
            "digital_twin": self._model_score(calibration_status),
            "measurement_quality": self._measurement_score(snapshot),
        }
        weights = {
            "comfort": 0.30,
            "hydraulic": 0.20,
            "thermal_transfer": 0.25,
            "digital_twin": 0.15,
            "measurement_quality": 0.10,
        }
        weighted = sum(components[name][0] * weights[name] for name in components)
        score = int(round(_clamp(weighted)))
        details = {
            name: {
                "score": int(round(value[0])),
                "weight_percent": int(round(weights[name] * 100)),
                "reason": value[1],
            }
            for name, value in components.items()
        }
        limiting = min(details.items(), key=lambda item: item[1]["score"])
        recommendations: list[str] = []
        if details["measurement_quality"]["score"] < 70:
            recommendations.append("Compléter ou fiabiliser les mesures manquantes avant d'interpréter le GEI.")
        if pump_on and details["hydraulic"]["score"] < 60:
            recommendations.append("Vérifier le débit, le circulateur et l'ouverture hydraulique.")
        if pump_on and details["thermal_transfer"]["score"] < 60:
            recommendations.append("Vérifier l'échange thermique, les températures et le débit réel.")
        if details["digital_twin"]["score"] < 60:
            recommendations.append("Poursuivre la collecte prévision/réel pour calibrer le modèle.")
        if not recommendations:
            recommendations.append("Performance cohérente avec les mesures disponibles.")

        item = {
            "component": "geocooling_efficiency_index",
            "version": self.VERSION,
            "generated_at": _now(),
            "read_only": True,
            "score": score,
            "grade": self._grade(score),
            "limiting_factor": {"name": limiting[0], **limiting[1]},
            "components": details,
            "operating_context": {
                "pump_state": pump_state,
                "indoor_temperature_c": indoor,
                "flow_l_min": flow,
                "thermal_power_w": power_w,
                "delta_t_c": delta_t,
            },
            "recommendations": recommendations,
            "calibration_phase": calibration_status.get("phase"),
        }
        if persist:
            with self._lock:
                self._history.append(item)
                self._persist(item)
        return deepcopy(item)

    def history(self, limit: int = 100) -> dict[str, Any]:
        limit = max(1, min(int(limit), self._capacity))
        with self._lock:
            items = deepcopy(list(self._history)[-limit:])
        scores = [_number(item.get("score")) for item in items]
        scores = [value for value in scores if value is not None]
        return {
            "count": len(items),
            "limit": limit,
            "average_score": round(sum(scores) / len(scores), 2) if scores else None,
            "minimum_score": int(min(scores)) if scores else None,
            "maximum_score": int(max(scores)) if scores else None,
            "items": items,
        }

    def status(self) -> dict[str, Any]:
        return {
            "component": "geocooling_efficiency_index",
            "version": self.VERSION,
            "read_only": True,
            "history_count": len(self._history),
            "storage": {"path": str(self._path), "last_error": self._last_error},
        }
