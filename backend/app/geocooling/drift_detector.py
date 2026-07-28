"""C023.4 — Détection consultative des dérives GeoCooling.

Analyse les historiques GEI et de calibration du jumeau numérique afin de
repérer des variations durables de performance. Ce composant est strictement
en lecture seule : il ne modifie aucun paramètre et ne pilote aucun actionneur.
"""
from __future__ import annotations

import json
import math
import os
import threading
from collections import Counter, deque
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _num(value: Any) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _pct_change(current: float, baseline: float) -> float | None:
    if abs(baseline) < 1e-9:
        return None
    return (current - baseline) / abs(baseline) * 100.0


class GeoCoolingDriftDetector:
    VERSION = "C023.4"

    def __init__(self, *, efficiency_index: Any, calibration: Any, digital_twin: Any) -> None:
        self.efficiency_index = efficiency_index
        self.calibration = calibration
        self.digital_twin = digital_twin
        self._lock = threading.RLock()
        self._capacity = max(20, int(os.getenv("GEOCOOLING_DRIFT_HISTORY_CAPACITY", "500")))
        self._history: deque[dict[str, Any]] = deque(maxlen=self._capacity)
        data_dir = Path(os.getenv("GEOCOOLING_DATA_DIR", "/app/data/geocooling"))
        self._path = Path(os.getenv("GEOCOOLING_DRIFT_FILE", str(data_dir / "drift-analysis.jsonl")))
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
                if isinstance(item, dict) and item.get("component") == "geocooling_drift_detector":
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
    def _severity(rank: int) -> str:
        return {0: "NONE", 1: "INFO", 2: "WARNING", 3: "CRITICAL"}.get(rank, "WARNING")

    @staticmethod
    def _split(values: list[float], recent_size: int = 5, baseline_size: int = 20) -> tuple[list[float], list[float]]:
        recent = values[-recent_size:]
        before = values[:-recent_size]
        baseline = before[-baseline_size:]
        return baseline, recent

    @staticmethod
    def _trend(values: list[float]) -> str:
        if len(values) < 3:
            return "UNKNOWN"
        n = len(values)
        x_mean = (n - 1) / 2
        y_mean = mean(values)
        den = sum((i - x_mean) ** 2 for i in range(n))
        slope = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values)) / den if den else 0.0
        if slope > 0.5:
            return "IMPROVING"
        if slope < -0.5:
            return "DEGRADING"
        return "STABLE"

    def _gei_analysis(self) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        history = self.efficiency_index.history(limit=200)
        items = history.get("items", []) if isinstance(history, dict) else []
        scores = [_num(item.get("score")) for item in items if isinstance(item, dict)]
        scores = [v for v in scores if v is not None]
        baseline, recent = self._split(scores)
        alerts: list[dict[str, Any]] = []
        baseline_avg = mean(baseline) if baseline else None
        recent_avg = mean(recent) if recent else None
        delta = None if baseline_avg is None or recent_avg is None else recent_avg - baseline_avg
        if len(baseline) >= 5 and len(recent) >= 3 and delta is not None:
            if delta <= -20:
                alerts.append({
                    "code": "GEI_MAJOR_DEGRADATION", "severity": "CRITICAL",
                    "title": "Dégradation majeure de l'efficacité globale",
                    "evidence": f"GEI récent inférieur de {abs(delta):.1f} points à la référence.",
                    "recommendation": "Contrôler en priorité le débit, les températures, les sondes et l'état hydraulique.",
                })
            elif delta <= -10:
                alerts.append({
                    "code": "GEI_DEGRADATION", "severity": "WARNING",
                    "title": "Baisse durable de l'efficacité globale",
                    "evidence": f"GEI récent inférieur de {abs(delta):.1f} points à la référence.",
                    "recommendation": "Comparer les composantes GEI et vérifier le facteur limitant dominant.",
                })
        limiting = [str(item.get("limiting_factor", {}).get("name")) for item in items[-20:] if isinstance(item, dict)]
        common = Counter(v for v in limiting if v and v != "None").most_common(1)
        if common and common[0][1] >= 5:
            alerts.append({
                "code": "RECURRING_LIMITING_FACTOR", "severity": "INFO",
                "title": "Facteur limitant récurrent",
                "evidence": f"{common[0][0]} est limitant dans {common[0][1]} évaluations récentes.",
                "recommendation": "Traiter ce facteur avant d'ajuster les seuils de pilotage.",
            })
        return {
            "samples": len(scores),
            "baseline_samples": len(baseline),
            "recent_samples": len(recent),
            "baseline_average": round(baseline_avg, 2) if baseline_avg is not None else None,
            "recent_average": round(recent_avg, 2) if recent_avg is not None else None,
            "delta_points": round(delta, 2) if delta is not None else None,
            "trend": self._trend(scores[-20:]),
            "recurring_limiting_factor": common[0][0] if common else None,
        }, alerts

    def _calibration_analysis(self) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        rows = self.calibration.history(limit=200)
        errors = [_num(row.get("absolute_error_c")) for row in rows if isinstance(row, dict)]
        errors = [v for v in errors if v is not None]
        baseline, recent = self._split(errors)
        alerts: list[dict[str, Any]] = []
        baseline_mae = mean(baseline) if baseline else None
        recent_mae = mean(recent) if recent else None
        change = None if baseline_mae is None or recent_mae is None else _pct_change(recent_mae, baseline_mae)
        if len(baseline) >= 5 and len(recent) >= 3 and change is not None:
            if change >= 100 and recent_mae >= 1.0:
                alerts.append({
                    "code": "MODEL_ACCURACY_MAJOR_DRIFT", "severity": "CRITICAL",
                    "title": "Forte dérive du modèle thermique",
                    "evidence": f"Erreur récente {recent_mae:.2f} °C, soit +{change:.0f} % par rapport à la référence.",
                    "recommendation": "Vérifier les sondes et les changements hydrauliques avant toute recalibration.",
                })
            elif change >= 50 and recent_mae >= 0.5:
                alerts.append({
                    "code": "MODEL_ACCURACY_DRIFT", "severity": "WARNING",
                    "title": "Précision du jumeau numérique en baisse",
                    "evidence": f"Erreur récente {recent_mae:.2f} °C, soit +{change:.0f} %.",
                    "recommendation": "Poursuivre les observations et contrôler les paramètres d'inertie et de puissance.",
                })
        biases = [_num(row.get("error_c")) for row in rows[-20:] if isinstance(row, dict)]
        biases = [v for v in biases if v is not None]
        bias = mean(biases) if biases else None
        if bias is not None and len(biases) >= 5 and abs(bias) >= 0.75:
            direction = "sous-estime" if bias > 0 else "surestime"
            alerts.append({
                "code": "MODEL_SYSTEMATIC_BIAS", "severity": "WARNING",
                "title": "Biais systématique du modèle",
                "evidence": f"Le modèle {direction} la température de {abs(bias):.2f} °C en moyenne.",
                "recommendation": "Examiner les paramètres du modèle ; aucune modification automatique ne sera appliquée.",
            })
        return {
            "samples": len(errors),
            "baseline_samples": len(baseline),
            "recent_samples": len(recent),
            "baseline_mae_c": round(baseline_mae, 3) if baseline_mae is not None else None,
            "recent_mae_c": round(recent_mae, 3) if recent_mae is not None else None,
            "mae_change_percent": round(change, 1) if change is not None else None,
            "recent_bias_c": round(bias, 3) if bias is not None else None,
        }, alerts

    def _measurement_analysis(self) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        try:
            snapshot = self.digital_twin.snapshot(refresh=True)
        except Exception as exc:
            return {"available": False, "error": str(exc)}, [{
                "code": "DIGITAL_TWIN_UNAVAILABLE", "severity": "WARNING",
                "title": "Jumeau numérique indisponible",
                "evidence": str(exc),
                "recommendation": "Vérifier l'API thermique et la disponibilité des mesures.",
            }]
        quality = snapshot.get("quality", {}) if isinstance(snapshot, dict) else {}
        available = int(quality.get("available_measurements", 0) or 0)
        missing = quality.get("missing_measurements", []) or []
        total = available + len(missing)
        ratio = available / total * 100 if total else 0.0
        alerts: list[dict[str, Any]] = []
        if total == 0 or ratio < 50:
            alerts.append({
                "code": "MEASUREMENT_COVERAGE_LOW", "severity": "WARNING",
                "title": "Couverture des mesures insuffisante",
                "evidence": f"{available}/{total} mesures disponibles.",
                "recommendation": "Rétablir les sondes manquantes avant d'interpréter les dérives.",
            })
        return {
            "available": True,
            "available_measurements": available,
            "missing_measurements": missing,
            "coverage_percent": round(ratio, 1),
        }, alerts

    def analyze(self, *, persist: bool = True) -> dict[str, Any]:
        gei, alerts_gei = self._gei_analysis()
        calibration, alerts_cal = self._calibration_analysis()
        measurements, alerts_measure = self._measurement_analysis()
        alerts = alerts_gei + alerts_cal + alerts_measure
        rank = {"NONE": 0, "INFO": 1, "WARNING": 2, "CRITICAL": 3}
        max_rank = max((rank.get(a.get("severity", "WARNING"), 2) for a in alerts), default=0)
        status = "NORMAL"
        if max_rank >= 3:
            status = "CRITICAL_DRIFT"
        elif max_rank >= 2:
            status = "DRIFT_DETECTED"
        elif max_rank == 1:
            status = "WATCH"
        confidence_samples = min(100, (gei["samples"] + calibration["samples"]) * 3)
        coverage = _num(measurements.get("coverage_percent")) or 0.0
        confidence = int(round(min(100.0, confidence_samples * 0.7 + coverage * 0.3)))
        item = {
            "component": "geocooling_drift_detector",
            "version": self.VERSION,
            "generated_at": _now(),
            "read_only": True,
            "status": status,
            "severity": self._severity(max_rank),
            "confidence_percent": confidence,
            "sufficient_history": gei["baseline_samples"] >= 5 or calibration["baseline_samples"] >= 5,
            "analysis": {
                "efficiency": gei,
                "digital_twin_accuracy": calibration,
                "measurements": measurements,
            },
            "alert_count": len(alerts),
            "alerts": alerts,
            "recommendation": (
                "Aucune dérive significative détectée avec les données disponibles."
                if not alerts else
                "Traiter d'abord les alertes critiques, puis les avertissements ; aucune correction automatique n'est appliquée."
            ),
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
        counts = Counter(item.get("status", "UNKNOWN") for item in items)
        return {"count": len(items), "limit": limit, "status_counts": dict(counts), "items": items}

    def status(self) -> dict[str, Any]:
        return {
            "component": "geocooling_drift_detector",
            "version": self.VERSION,
            "read_only": True,
            "history_count": len(self._history),
            "capacity": self._capacity,
            "storage": {"path": str(self._path), "last_error": self._last_error},
            "thresholds": {
                "gei_warning_drop_points": 10,
                "gei_critical_drop_points": 20,
                "model_warning_mae_increase_percent": 50,
                "model_critical_mae_increase_percent": 100,
                "systematic_bias_c": 0.75,
            },
        }
