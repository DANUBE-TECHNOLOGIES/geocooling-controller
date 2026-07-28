"""C023.5 — Auto-calibration assistée GeoCooling.

Produit des propositions explicables à partir de la calibration du jumeau
numérique et des dérives détectées. Le composant ne modifie jamais les
paramètres du Brain ni les actionneurs. Les décisions humaines sont journalisées.
"""
from __future__ import annotations

import json
import math
import os
import threading
import uuid
from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _num(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


class AssistedCalibrationEngine:
    VERSION = "C023.5"
    ALLOWED_DECISIONS = {"ACCEPTED", "REJECTED", "DEFERRED"}

    def __init__(self, *, calibration: Any, drift_detector: Any, controller: Any | None = None) -> None:
        self.calibration = calibration
        self.drift_detector = drift_detector
        self.controller = controller
        self._lock = threading.RLock()
        self._capacity = max(20, int(os.getenv("GEOCOOLING_ASSISTED_CALIBRATION_CAPACITY", "500")))
        self._history: deque[dict[str, Any]] = deque(maxlen=self._capacity)
        data_dir = Path(os.getenv("GEOCOOLING_DATA_DIR", "/app/data/geocooling"))
        self._path = Path(os.getenv(
            "GEOCOOLING_ASSISTED_CALIBRATION_FILE",
            str(data_dir / "assisted-calibration.jsonl"),
        ))
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
                if isinstance(item, dict) and item.get("component") == "assisted_calibration":
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
    def _proposal(*, code: str, parameter: str, current: float | None,
                  suggested: float | None, unit: str, confidence: int,
                  reason: str, evidence: list[str], guardrails: list[str]) -> dict[str, Any]:
        delta = None
        if current is not None and suggested is not None:
            delta = round(suggested - current, 3)
        return {
            "proposal_id": str(uuid.uuid4()),
            "code": code,
            "parameter": parameter,
            "current_value": current,
            "suggested_value": suggested,
            "delta": delta,
            "unit": unit,
            "confidence_percent": max(0, min(100, int(confidence))),
            "reason": reason,
            "evidence": evidence,
            "guardrails": guardrails,
            "application": "MANUAL_ONLY",
        }

    def _controller_value(self, *names: str) -> float | None:
        targets = [self.controller, getattr(self.controller, "brain", None)]
        for target in targets:
            if target is None:
                continue
            for name in names:
                value = _num(getattr(target, name, None))
                if value is not None:
                    return value
        return None

    def recommendations(self, *, persist: bool = False) -> dict[str, Any]:
        calibration = self.calibration.status(evaluate_due=True)
        drift = self.drift_detector.analyze(persist=False)
        metrics = calibration.get("prediction_accuracy", {}) if isinstance(calibration, dict) else {}
        adaptive = calibration.get("adaptive_model", {}) if isinstance(calibration, dict) else {}
        sample_count = int(metrics.get("sample_count", 0) or 0)
        mae = _num(metrics.get("mean_absolute_error_c"))
        bias = _num(metrics.get("mean_bias_c"))
        calibration_level = int(calibration.get("calibration_level_percent", 0) or 0)
        alerts = drift.get("alerts", []) if isinstance(drift, dict) else []
        alert_codes = {str(a.get("code")) for a in alerts if isinstance(a, dict)}

        proposals: list[dict[str, Any]] = []
        blockers: list[str] = []
        if sample_count < 8:
            blockers.append(f"Échantillonnage insuffisant : {sample_count}/8 observations minimum.")
        if calibration_level < 40:
            blockers.append(f"Calibration insuffisante : {calibration_level}%/40% minimum.")
        if "DIGITAL_TWIN_UNAVAILABLE" in alert_codes:
            blockers.append("Jumeau numérique indisponible.")
        if "MEASUREMENT_COVERAGE_LOW" in alert_codes:
            blockers.append("Couverture des mesures insuffisante.")

        eligible = not blockers
        confidence = min(95, max(20, round(calibration_level * 0.7 + min(sample_count, 30))))

        if eligible and bias is not None and abs(bias) >= 0.25:
            # Correction bornée et prudente : 50 % du biais, maximum 0,5 °C.
            correction = max(-0.5, min(0.5, bias * 0.5))
            current_offset = self._controller_value("forecast_temperature_offset_c", "temperature_offset_c") or 0.0
            suggested = round(current_offset + correction, 2)
            proposals.append(self._proposal(
                code="FORECAST_TEMPERATURE_OFFSET",
                parameter="forecast_temperature_offset_c",
                current=round(current_offset, 2),
                suggested=suggested,
                unit="°C",
                confidence=confidence,
                reason="Réduire le biais systématique entre température prévue et observée.",
                evidence=[
                    f"Biais moyen observé : {bias:+.3f} °C.",
                    f"Erreur absolue moyenne : {mae:.3f} °C." if mae is not None else "MAE indisponible.",
                    f"Échantillons analysés : {sample_count}.",
                ],
                guardrails=[
                    "Correction limitée à ±0,50 °C par proposition.",
                    "Observer au moins 5 nouveaux résultats avant une autre modification.",
                    "Ne pas appliquer si une sonde a été déplacée ou remplacée récemment.",
                ],
            ))

        adaptive_inertia = _num(adaptive.get("thermal_inertia_factor") or adaptive.get("inertia_factor"))
        if eligible and mae is not None and mae >= 0.60 and adaptive_inertia is not None:
            # Proposition informative très bornée, dans le sens suggéré par le biais.
            direction = 1.0 if (bias or 0.0) > 0 else -1.0
            change = max(-0.10, min(0.10, direction * 0.05))
            suggested = round(adaptive_inertia * (1.0 + change), 3)
            proposals.append(self._proposal(
                code="THERMAL_INERTIA_REVIEW",
                parameter="thermal_inertia_factor",
                current=round(adaptive_inertia, 3),
                suggested=suggested,
                unit="ratio",
                confidence=max(20, confidence - 15),
                reason="Tester une correction prudente de l'inertie thermique du modèle.",
                evidence=[
                    f"MAE actuelle : {mae:.3f} °C.",
                    f"Biais moyen : {(bias or 0.0):+.3f} °C.",
                    "La proposition est limitée à 5 % de la valeur courante.",
                ],
                guardrails=[
                    "Appliquer un seul changement de modèle à la fois.",
                    "Conserver la valeur précédente pour retour arrière.",
                    "Ne jamais utiliser cette proposition comme seuil de sécurité condensation.",
                ],
            ))

        if any(code in alert_codes for code in {"GEI_DEGRADATION", "GEI_MAJOR_DEGRADATION", "MODEL_ACCURACY_MAJOR_DRIFT"}):
            blockers.append("Dérive importante détectée : diagnostic matériel/mesures prioritaire avant recalibration.")
            proposals = []
            eligible = False

        payload = {
            "component": "assisted_calibration",
            "version": self.VERSION,
            "generated_at": _now(),
            "read_only": True,
            "automatic_application": False,
            "eligible": eligible,
            "calibration_level_percent": calibration_level,
            "sample_count": sample_count,
            "mean_absolute_error_c": mae,
            "mean_bias_c": bias,
            "blockers": blockers,
            "proposal_count": len(proposals),
            "proposals": proposals,
            "required_workflow": [
                "Examiner les preuves et garde-fous.",
                "Accepter, différer ou rejeter la proposition.",
                "Appliquer séparément le changement après sauvegarde.",
                "Observer les nouvelles mesures avant toute autre correction.",
            ],
        }
        if persist:
            event = deepcopy(payload)
            event.update({"event_id": str(uuid.uuid4()), "event_type": "RECOMMENDATION_SET"})
            with self._lock:
                self._history.append(event)
                self._persist(event)
        return payload

    def decide(self, *, proposal: dict[str, Any], decision: str, note: str | None = None,
               decided_by: str = "operator") -> dict[str, Any]:
        normalized = str(decision).strip().upper()
        if normalized not in self.ALLOWED_DECISIONS:
            raise ValueError("Décision autorisée : ACCEPTED, REJECTED ou DEFERRED")
        if not isinstance(proposal, dict) or not proposal.get("proposal_id"):
            raise ValueError("Proposition complète avec proposal_id obligatoire")
        event = {
            "component": "assisted_calibration",
            "version": self.VERSION,
            "event_id": str(uuid.uuid4()),
            "event_type": "OPERATOR_DECISION",
            "decided_at": _now(),
            "decided_by": decided_by,
            "decision": normalized,
            "note": note,
            "proposal": deepcopy(proposal),
            "applied": False,
            "application_message": "Décision enregistrée uniquement ; aucun paramètre n'a été modifié.",
        }
        with self._lock:
            self._history.append(event)
            self._persist(event)
        return deepcopy(event)

    def history(self, limit: int = 100) -> dict[str, Any]:
        limit = max(1, min(int(limit), self._capacity))
        with self._lock:
            items = deepcopy(list(self._history)[-limit:])
        return {"count": len(items), "items": items}

    def status(self) -> dict[str, Any]:
        decisions = [i for i in self._history if i.get("event_type") == "OPERATOR_DECISION"]
        return {
            "component": "assisted_calibration",
            "version": self.VERSION,
            "read_only": True,
            "automatic_application": False,
            "history_count": len(self._history),
            "operator_decisions": len(decisions),
            "last_decision": deepcopy(decisions[-1]) if decisions else None,
            "storage": {"path": str(self._path), "last_error": self._last_error},
        }
