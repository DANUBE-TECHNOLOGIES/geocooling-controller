from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class GeoCoolingBrainV5:
    """Explainable advisory decision layer built on the H020 optimizer."""

    VERSION = "H021-BRAIN-V5-1.0"

    def __init__(self, optimizer: Any, confidence: Any, orchestrator: Any) -> None:
        self.optimizer = optimizer
        self.confidence = confidence
        self.orchestrator = orchestrator
        self.last_decision: dict[str, Any] | None = None

    def status(self) -> dict[str, Any]:
        return {
            "generated_at": utc_now_iso(),
            "version": self.VERSION,
            "advisory_only": True,
            "physical_activation_allowed": False,
            "hardware_touched": False,
            "last_decision": self.last_decision,
        }

    def decide(self, payload: dict[str, Any]) -> dict[str, Any]:
        plan = self.optimizer.optimize(payload)
        runtime = int(plan.get("recommended_runtime_minutes") or 0)
        action = str(plan.get("recommended_action") or "HOLD")
        condensation = bool((plan.get("optimized") or {}).get("condensation_interlock"))
        confidence_score = 0.90
        risks: list[dict[str, Any]] = []
        reasons: list[str] = []

        if condensation:
            confidence_score -= 0.45
            risks.append({"code": "CONDENSATION_INTERLOCK", "severity": "CRITICAL", "message": "La marge anti-condensation n'est pas garantie."})
        if runtime >= 300:
            confidence_score -= 0.10
            risks.append({"code": "LONG_RUNTIME", "severity": "WARNING", "message": "Le cycle conseillé est long et devra être surveillé."})
        if float(plan.get("efficiency_index") or 0.0) < 0.25 and action == "COOL":
            confidence_score -= 0.15
            risks.append({"code": "LOW_EFFICIENCY", "severity": "WARNING", "message": "Le gain thermique estimé est faible au regard de l'énergie consommée."})

        if action == "COOL":
            reasons.append("La prévision montre un bénéfice thermique supérieur au scénario sans refroidissement.")
            reasons.append("Un cycle long unique limite les démarrages et la consommation auxiliaire.")
        else:
            reasons.append("Le scénario sans refroidissement reste compatible avec l'objectif de confort.")
            reasons.append("Aucune consommation n'est recommandée tant que le bénéfice thermique reste insuffisant.")

        alternatives = [
            {"action": "HOLD", "impact": "Énergie minimale, confort potentiellement moins bon", "allowed": True},
            {"action": "COOL_LATER", "impact": "Décale le cycle vers une fenêtre plus favorable", "allowed": action == "COOL" and plan.get("recommended_start_hour", 0) > 0},
        ]
        if condensation:
            action = "BLOCKED"
            runtime = 0
            reasons.insert(0, "La sécurité condensation impose le maintien à l'arrêt.")

        confidence_score = max(0.0, min(1.0, confidence_score))
        confidence_level = "HIGH" if confidence_score >= 0.8 else "MEDIUM" if confidence_score >= 0.55 else "LOW"
        decision = {
            "generated_at": utc_now_iso(),
            "version": self.VERSION,
            "decision": action,
            "why": reasons,
            "confidence": {"score": round(confidence_score, 3), "level": confidence_level},
            "risks": risks,
            "alternatives": alternatives,
            "timing": {
                "recommended_start_hour": plan.get("recommended_start_hour"),
                "recommended_runtime_minutes": runtime,
            },
            "targets": {
                "target_temperature_c": payload.get("target_temperature_c"),
                "predicted_final_temperature_c": (plan.get("optimized") or {}).get("final_temperature_c"),
            },
            "impacts": {
                "estimated_energy_kwh": plan.get("estimated_energy_kwh"),
                "thermal_gain_c": plan.get("thermal_gain_c"),
                "efficiency_index": plan.get("efficiency_index"),
                "estimated_starts": plan.get("estimated_starts"),
                "condensation_interlock": condensation,
            },
            "plan": plan,
            "advisory_only": True,
            "automatic_execution_allowed": False,
            "physical_activation_allowed": False,
            "hardware_touched": False,
        }
        self.last_decision = decision
        return decision
