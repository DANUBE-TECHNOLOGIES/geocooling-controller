from __future__ import annotations

import json
import os

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.geocooling.brain_v2.decision.advisory_decision_engine import (
    AdvisoryDecisionEngine,
)

from app.geocooling.brain_v2.decision.automatic_advisor import (
    AutomaticAdvisoryOrchestrator,
)

from app.geocooling.brain_v2.learning.automatic_collector import (
    AutomaticObservationCollector,
)

from app.geocooling.brain_v2.prediction.thermal_prediction_engine import (
    ThermalPredictionEngine,
)


class HomeAssistantBridge:
    VERSION = "C022.7-HOME-ASSISTANT-BRIDGE-1.0"

    ACTION_LABELS = {
        "WAIT_FOR_DATA": "Attente de données",
        "STOP_OR_BLOCK_COOLING": "Blocage du refroidissement",
        "RECOMMEND_STOP_COOLING": "Arrêt conseillé",
        "MAINTAIN_IDLE": "Maintien au repos",
        "CONTINUE_WITH_CAUTION": "Poursuite prudente",
        "RECOMMEND_CONTINUE_COOLING": "Poursuite conseillée",
        "REASSESS_COOLING": "Réévaluation nécessaire",
        "MONITOR_BEFORE_COOLING": "Surveillance avant démarrage",
        "RECOMMEND_START_COOLING": "Démarrage conseillé",
        "MONITOR_THERMAL_EVOLUTION": "Surveillance thermique",
        "MAINTAIN_CURRENT_STATE": "Maintien de l’état actuel",
    }

    PRIORITY_LABELS = {
        "LOW": "Faible",
        "NORMAL": "Normale",
        "HIGH": "Haute",
        "CRITICAL": "Critique",
    }

    STATUS_LABELS = {
        "COLLECTING": "Collecte",
        "LIMITED": "Données limitées",
        "LEARNING": "Apprentissage",
        "READY": "Prêt",
    }

    CONDENSATION_LABELS = {
        "UNKNOWN": "Inconnue",
        "SAFE": "Sûre",
        "WARNING": "Attention",
        "CRITICAL": "Critique",
    }

    def __init__(
        self,
        data_directory: str | Path | None = None,
    ) -> None:
        configured_directory = (
            data_directory
            or os.getenv(
                "GEOCOOLING_BRAIN_V2_DATA_DIR",
                "/app/data/geocooling/brain_v2",
            )
        )

        self.data_directory = Path(
            configured_directory
        )

        self.advisor = AutomaticAdvisoryOrchestrator(
            data_directory=self.data_directory
        )

        self.decision_engine = AdvisoryDecisionEngine(
            data_directory=self.data_directory
        )

        self.prediction_engine = ThermalPredictionEngine(
            data_directory=self.data_directory
        )

        self.collector = AutomaticObservationCollector(
            data_directory=self.data_directory
        )

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(
            timezone.utc
        ).isoformat()

    @staticmethod
    def _safe_round(
        value: Any,
        digits: int = 2,
    ) -> float | None:
        if value is None or isinstance(
            value,
            bool,
        ):
            return None

        try:
            return round(
                float(value),
                digits,
            )
        except (
            TypeError,
            ValueError,
        ):
            return None

    @staticmethod
    def _safe_int(
        value: Any,
    ) -> int | None:
        if value is None or isinstance(
            value,
            bool,
        ):
            return None

        try:
            return int(
                round(
                    float(value)
                )
            )
        except (
            TypeError,
            ValueError,
        ):
            return None

    def _latest_snapshot(
        self,
    ) -> dict[str, Any]:
        try:
            return self.advisor.latest_snapshot()
        except Exception:
            return {}

    def state(
        self,
    ) -> dict[str, Any]:
        snapshot = self._latest_snapshot()

        prediction_status = (
            self.prediction_engine.status()
        )

        collector_status = (
            self.collector.status()
        )

        advisor_status = (
            self.advisor.status()
        )

        decision_status = (
            self.decision_engine.status()
        )

        action = snapshot.get(
            "action",
            "WAIT_FOR_DATA",
        )

        priority = snapshot.get(
            "priority",
            "LOW",
        )

        brain_status = snapshot.get(
            "status",
            prediction_status.get(
                "status",
                "COLLECTING",
            ),
        )

        condensation_status = snapshot.get(
            "condensation_status",
            "UNKNOWN",
        )

        collector_running = bool(
            collector_status.get(
                "running",
                False,
            )
        )

        advisor_running = bool(
            advisor_status.get(
                "running",
                False,
            )
        )

        available = bool(
            collector_running
            and advisor_running
            and snapshot
        )

        confidence = self._safe_round(
            snapshot.get(
                "confidence_percent"
            ),
            1,
        )

        observations = self._safe_int(
            snapshot.get(
                "observations_used",
                prediction_status.get(
                    "observations_available"
                ),
            )
        )

        minutes_to_target = self._safe_int(
            snapshot.get(
                "minutes_to_target"
            )
        )

        return {
            "version": self.VERSION,
            "generated_at": self._utc_now(),
            "available": available,
            "mode": "ADVISORY_ONLY",
            "mode_label": "Conseil uniquement",
            "brain_status": brain_status,
            "brain_status_label": (
                self.STATUS_LABELS.get(
                    brain_status,
                    brain_status,
                )
            ),
            "action": action,
            "action_label": (
                self.ACTION_LABELS.get(
                    action,
                    action,
                )
            ),
            "priority": priority,
            "priority_label": (
                self.PRIORITY_LABELS.get(
                    priority,
                    priority,
                )
            ),
            "summary": snapshot.get(
                "summary",
                "Aucune recommandation disponible.",
            ),
            "confidence_percent": confidence,
            "observations_used": observations,
            "indoor_temperature_c": self._safe_round(
                snapshot.get(
                    "indoor_temperature_c"
                )
            ),
            "outdoor_temperature_c": self._safe_round(
                snapshot.get(
                    "outdoor_temperature_c"
                )
            ),
            "indoor_humidity_percent": self._safe_round(
                snapshot.get(
                    "indoor_humidity_percent"
                ),
                1,
            ),
            "floor_surface_temperature_c": self._safe_round(
                snapshot.get(
                    "floor_surface_temperature_c"
                )
            ),
            "floor_supply_temperature_c": self._safe_round(
                snapshot.get(
                    "floor_supply_temperature_c"
                )
            ),
            "floor_return_temperature_c": self._safe_round(
                snapshot.get(
                    "floor_return_temperature_c"
                )
            ),
            "target_temperature_c": self._safe_round(
                snapshot.get(
                    "target_temperature_c"
                )
            ),
            "start_threshold_c": self._safe_round(
                snapshot.get(
                    "start_threshold_c"
                )
            ),
            "stop_threshold_c": self._safe_round(
                snapshot.get(
                    "stop_threshold_c"
                )
            ),
            "active_cooling": bool(
                snapshot.get(
                    "active_cooling",
                    False,
                )
            ),
            "pump_running": bool(
                snapshot.get(
                    "pump_running",
                    False,
                )
            ),
            "valve_open": bool(
                snapshot.get(
                    "valve_open",
                    False,
                )
            ),
            "cooling_benefit_c": self._safe_round(
                snapshot.get(
                    "cooling_benefit_c"
                )
            ),
            "minutes_to_target": minutes_to_target,
            "predicted_cooling_temperature_c": self._safe_round(
                snapshot.get(
                    "predicted_cooling_temperature_c"
                )
            ),
            "predicted_passive_temperature_c": self._safe_round(
                snapshot.get(
                    "predicted_passive_temperature_c"
                )
            ),
            "cooling_rate_c_per_hour": self._safe_round(
                snapshot.get(
                    "cooling_rate_c_per_hour"
                ),
                4,
            ),
            "passive_rate_c_per_hour": self._safe_round(
                snapshot.get(
                    "passive_rate_c_per_hour"
                ),
                4,
            ),
            "condensation_status": condensation_status,
            "condensation_status_label": (
                self.CONDENSATION_LABELS.get(
                    condensation_status,
                    condensation_status,
                )
            ),
            "dew_point_c": self._safe_round(
                snapshot.get(
                    "dew_point_c"
                )
            ),
            "condensation_margin_c": self._safe_round(
                snapshot.get(
                    "condensation_margin_c"
                )
            ),
            "condensation_safe": snapshot.get(
                "condensation_safe"
            ),
            "reason_codes": snapshot.get(
                "reason_codes",
                [],
            ),
            "collector_running": collector_running,
            "collector_interval_seconds": (
                collector_status.get(
                    "collection_interval_seconds"
                )
            ),
            "collector_successful_collections": (
                collector_status.get(
                    "successful_collections",
                    0,
                )
            ),
            "advisor_running": advisor_running,
            "advisor_interval_seconds": (
                advisor_status.get(
                    "evaluation_interval_seconds"
                )
            ),
            "advisor_successful_evaluations": (
                advisor_status.get(
                    "successful_evaluations",
                    0,
                )
            ),
            "prediction_model_exists": (
                prediction_status.get(
                    "model_exists",
                    False,
                )
            ),
            "decision_history_exists": (
                decision_status.get(
                    "history_exists",
                    False,
                )
            ),
            "advisory_only": True,
            "decision_authority": False,
            "hardware_control": False,
            "mqtt_publish": False,
            "modbus_command": False,
            "relay_command": False,
        }

    @staticmethod
    def _api_url(
        base_url: str,
    ) -> str:
        return (
            base_url.rstrip("/")
            + "/geocooling/brain-v2/integration/home-assistant/state"
        )

    def package_yaml(
        self,
        base_url: str,
    ) -> str:
        endpoint = self._api_url(
            base_url
        )

        return f"""# GeoCooling Brain V2 — C022.7
# Fichier à placer dans :
# /config/gc_packages/geocooling_brain_v2.yaml

rest:
  - resource: "{endpoint}"
    scan_interval: 60
    timeout: 10
    sensor:
      - name: GeoCooling Brain V2
        unique_id: geocooling_brain_v2
        value_template: "{{{{ value_json.action_label | default('Indisponible') }}}}"
        json_attributes:
          - version
          - generated_at
          - available
          - mode
          - mode_label
          - brain_status
          - brain_status_label
          - action
          - action_label
          - priority
          - priority_label
          - summary
          - confidence_percent
          - observations_used
          - indoor_temperature_c
          - outdoor_temperature_c
          - indoor_humidity_percent
          - floor_surface_temperature_c
          - floor_supply_temperature_c
          - floor_return_temperature_c
          - target_temperature_c
          - start_threshold_c
          - stop_threshold_c
          - active_cooling
          - pump_running
          - valve_open
          - cooling_benefit_c
          - minutes_to_target
          - predicted_cooling_temperature_c
          - predicted_passive_temperature_c
          - cooling_rate_c_per_hour
          - passive_rate_c_per_hour
          - condensation_status
          - condensation_status_label
          - dew_point_c
          - condensation_margin_c
          - condensation_safe
          - reason_codes
          - collector_running
          - collector_successful_collections
          - advisor_running
          - advisor_successful_evaluations
          - prediction_model_exists
          - decision_history_exists
          - advisory_only
          - decision_authority
          - hardware_control
          - mqtt_publish
          - modbus_command
          - relay_command

template:
  - binary_sensor:
      - name: GeoCooling Brain disponible
        unique_id: geocooling_brain_v2_available
        device_class: connectivity
        state: >
          {{{{ state_attr('sensor.geocooling_brain_v2', 'available') | default(false) }}}}

      - name: GeoCooling refroidissement actif
        unique_id: geocooling_brain_v2_cooling_active
        state: >
          {{{{ state_attr('sensor.geocooling_brain_v2', 'active_cooling') | default(false) }}}}

      - name: GeoCooling risque condensation
        unique_id: geocooling_brain_v2_condensation_risk
        device_class: problem
        state: >
          {{{{ state_attr('sensor.geocooling_brain_v2', 'condensation_safe') == false }}}}

      - name: GeoCooling recommandation démarrage
        unique_id: geocooling_brain_v2_start_recommended
        state: >
          {{{{ state_attr('sensor.geocooling_brain_v2', 'action') == 'RECOMMEND_START_COOLING' }}}}

      - name: GeoCooling recommandation arrêt
        unique_id: geocooling_brain_v2_stop_recommended
        state: >
          {{{{ state_attr('sensor.geocooling_brain_v2', 'action') in ['RECOMMEND_STOP_COOLING', 'STOP_OR_BLOCK_COOLING'] }}}}

  - sensor:
      - name: GeoCooling état Brain
        unique_id: geocooling_brain_v2_status
        state: >
          {{{{ state_attr('sensor.geocooling_brain_v2', 'brain_status_label') | default('Inconnu') }}}}
        icon: mdi:brain

      - name: GeoCooling décision Brain
        unique_id: geocooling_brain_v2_decision
        state: >
          {{{{ state_attr('sensor.geocooling_brain_v2', 'action_label') | default('Indisponible') }}}}
        attributes:
          code: >
            {{{{ state_attr('sensor.geocooling_brain_v2', 'action') }}}}
          résumé: >
            {{{{ state_attr('sensor.geocooling_brain_v2', 'summary') }}}}
          priorité: >
            {{{{ state_attr('sensor.geocooling_brain_v2', 'priority_label') }}}}
        icon: mdi:head-snowflake-outline

      - name: GeoCooling confiance Brain
        unique_id: geocooling_brain_v2_confidence
        state: >
          {{{{ state_attr('sensor.geocooling_brain_v2', 'confidence_percent') | float(0) }}}}
        unit_of_measurement: "%"
        state_class: measurement
        icon: mdi:gauge

      - name: GeoCooling observations Brain
        unique_id: geocooling_brain_v2_observations
        state: >
          {{{{ state_attr('sensor.geocooling_brain_v2', 'observations_used') | int(0) }}}}
        state_class: total
        icon: mdi:database-clock

      - name: GeoCooling température intérieure Brain
        unique_id: geocooling_brain_v2_indoor_temperature
        state: >
          {{{{ state_attr('sensor.geocooling_brain_v2', 'indoor_temperature_c') | float(0) }}}}
        unit_of_measurement: "°C"
        device_class: temperature
        state_class: measurement

      - name: GeoCooling température extérieure Brain
        unique_id: geocooling_brain_v2_outdoor_temperature
        state: >
          {{{{ state_attr('sensor.geocooling_brain_v2', 'outdoor_temperature_c') | float(0) }}}}
        unit_of_measurement: "°C"
        device_class: temperature
        state_class: measurement

      - name: GeoCooling humidité intérieure Brain
        unique_id: geocooling_brain_v2_indoor_humidity
        state: >
          {{{{ state_attr('sensor.geocooling_brain_v2', 'indoor_humidity_percent') | float(0) }}}}
        unit_of_measurement: "%"
        device_class: humidity
        state_class: measurement

      - name: GeoCooling température plancher
        unique_id: geocooling_brain_v2_floor_surface_temperature
        state: >
          {{{{ state_attr('sensor.geocooling_brain_v2', 'floor_surface_temperature_c') | float(0) }}}}
        unit_of_measurement: "°C"
        device_class: temperature
        state_class: measurement

      - name: GeoCooling température départ
        unique_id: geocooling_brain_v2_floor_supply_temperature
        state: >
          {{{{ state_attr('sensor.geocooling_brain_v2', 'floor_supply_temperature_c') | float(0) }}}}
        unit_of_measurement: "°C"
        device_class: temperature
        state_class: measurement

      - name: GeoCooling température retour
        unique_id: geocooling_brain_v2_floor_return_temperature
        state: >
          {{{{ state_attr('sensor.geocooling_brain_v2', 'floor_return_temperature_c') | float(0) }}}}
        unit_of_measurement: "°C"
        device_class: temperature
        state_class: measurement

      - name: GeoCooling cible Brain
        unique_id: geocooling_brain_v2_target_temperature
        state: >
          {{{{ state_attr('sensor.geocooling_brain_v2', 'target_temperature_c') | float(0) }}}}
        unit_of_measurement: "°C"
        device_class: temperature
        state_class: measurement

      - name: GeoCooling prévision avec refroidissement
        unique_id: geocooling_brain_v2_predicted_cooling_temperature
        state: >
          {{{{ state_attr('sensor.geocooling_brain_v2', 'predicted_cooling_temperature_c') | float(0) }}}}
        unit_of_measurement: "°C"
        device_class: temperature
        state_class: measurement

      - name: GeoCooling prévision sans refroidissement
        unique_id: geocooling_brain_v2_predicted_passive_temperature
        state: >
          {{{{ state_attr('sensor.geocooling_brain_v2', 'predicted_passive_temperature_c') | float(0) }}}}
        unit_of_measurement: "°C"
        device_class: temperature
        state_class: measurement

      - name: GeoCooling bénéfice refroidissement
        unique_id: geocooling_brain_v2_cooling_benefit
        state: >
          {{{{ state_attr('sensor.geocooling_brain_v2', 'cooling_benefit_c') | float(0) }}}}
        unit_of_measurement: "°C"
        state_class: measurement
        icon: mdi:snowflake-thermometer

      - name: GeoCooling délai cible
        unique_id: geocooling_brain_v2_minutes_to_target
        state: >
          {{{{ state_attr('sensor.geocooling_brain_v2', 'minutes_to_target') | int(0) }}}}
        unit_of_measurement: "min"
        state_class: measurement
        icon: mdi:timer-outline

      - name: GeoCooling point de rosée
        unique_id: geocooling_brain_v2_dew_point
        state: >
          {{{{ state_attr('sensor.geocooling_brain_v2', 'dew_point_c') | float(0) }}}}
        unit_of_measurement: "°C"
        device_class: temperature
        state_class: measurement

      - name: GeoCooling marge condensation
        unique_id: geocooling_brain_v2_condensation_margin
        state: >
          {{{{ state_attr('sensor.geocooling_brain_v2', 'condensation_margin_c') | float(0) }}}}
        unit_of_measurement: "°C"
        state_class: measurement
        icon: mdi:water-alert-outline

      - name: GeoCooling état condensation
        unique_id: geocooling_brain_v2_condensation_status
        state: >
          {{{{ state_attr('sensor.geocooling_brain_v2', 'condensation_status_label') | default('Inconnue') }}}}
        icon: mdi:water-check-outline
"""

    @staticmethod
    def dashboard_yaml() -> str:
        return """title: GeoCooling Brain V2
views:
  - title: Pilotage
    path: geocooling-brain-v2
    icon: mdi:home-thermometer-outline
    cards:
      - type: markdown
        content: |
          # GeoCooling Brain V2
          **{{ states('sensor.geocooling_decision_brain') }}**

          {{ state_attr('sensor.geocooling_decision_brain', 'résumé') }}

      - type: entities
        title: État du système
        show_header_toggle: false
        entities:
          - entity: binary_sensor.geocooling_brain_disponible
            name: Brain disponible
          - entity: sensor.geocooling_etat_brain
            name: Phase
          - entity: sensor.geocooling_decision_brain
            name: Recommandation
          - entity: sensor.geocooling_confiance_brain
            name: Confiance
          - entity: sensor.geocooling_observations_brain
            name: Observations apprises
          - entity: binary_sensor.geocooling_refroidissement_actif
            name: Refroidissement actif

      - type: gauge
        entity: sensor.geocooling_confiance_brain
        name: Confiance du Brain
        min: 0
        max: 100
        severity:
          red: 0
          yellow: 20
          green: 60

      - type: entities
        title: Températures
        show_header_toggle: false
        entities:
          - entity: sensor.geocooling_temperature_interieure_brain
            name: Intérieure
          - entity: sensor.geocooling_temperature_exterieure_brain
            name: Extérieure
          - entity: sensor.geocooling_temperature_plancher
            name: Surface du plancher
          - entity: sensor.geocooling_temperature_depart
            name: Départ plancher
          - entity: sensor.geocooling_temperature_retour
            name: Retour plancher
          - entity: sensor.geocooling_cible_brain
            name: Cible

      - type: history-graph
        title: Historique thermique
        hours_to_show: 24
        entities:
          - entity: sensor.geocooling_temperature_interieure_brain
            name: Intérieur
          - entity: sensor.geocooling_temperature_exterieure_brain
            name: Extérieur
          - entity: sensor.geocooling_temperature_plancher
            name: Plancher
          - entity: sensor.geocooling_temperature_depart
            name: Départ
          - entity: sensor.geocooling_temperature_retour
            name: Retour

      - type: entities
        title: Prévisions à six heures
        show_header_toggle: false
        entities:
          - entity: sensor.geocooling_prevision_avec_refroidissement
            name: Avec refroidissement
          - entity: sensor.geocooling_prevision_sans_refroidissement
            name: Sans refroidissement
          - entity: sensor.geocooling_benefice_refroidissement
            name: Bénéfice estimé
          - entity: sensor.geocooling_delai_cible
            name: Délai vers la cible

      - type: history-graph
        title: Prévisions comparées
        hours_to_show: 24
        entities:
          - entity: sensor.geocooling_prevision_avec_refroidissement
            name: Avec refroidissement
          - entity: sensor.geocooling_prevision_sans_refroidissement
            name: Sans refroidissement
          - entity: sensor.geocooling_temperature_interieure_brain
            name: Température réelle

      - type: entities
        title: Sécurité condensation
        show_header_toggle: false
        entities:
          - entity: binary_sensor.geocooling_risque_condensation
            name: Risque détecté
          - entity: sensor.geocooling_etat_condensation
            name: État
          - entity: sensor.geocooling_humidite_interieure_brain
            name: Humidité intérieure
          - entity: sensor.geocooling_point_de_rosee
            name: Point de rosée
          - entity: sensor.geocooling_marge_condensation
            name: Marge de sécurité

      - type: conditional
        conditions:
          - entity: binary_sensor.geocooling_risque_condensation
            state: "on"
        card:
          type: markdown
          content: |
            # ⚠️ Risque de condensation
            Le refroidissement ne doit pas être activé tant que la marge de sécurité est insuffisante.

      - type: conditional
        conditions:
          - entity: binary_sensor.geocooling_recommandation_demarrage
            state: "on"
        card:
          type: markdown
          content: |
            # ❄️ Démarrage conseillé
            Le Brain estime que le refroidissement apporterait un bénéfice thermique suffisant.

      - type: conditional
        conditions:
          - entity: binary_sensor.geocooling_recommandation_arret
            state: "on"
        card:
          type: markdown
          content: |
            # 🛑 Arrêt conseillé
            La température cible est atteinte ou une sécurité impose l’arrêt.
"""

    def status(
        self,
    ) -> dict[str, Any]:
        state = self.state()

        return {
            "version": self.VERSION,
            "status": (
                "READY"
                if state.get(
                    "available"
                )
                else "DEGRADED"
            ),
            "state_available": bool(
                state
            ),
            "brain_available": state.get(
                "available",
                False,
            ),
            "package_generation": True,
            "dashboard_generation": True,
            "advisory_only": True,
            "decision_authority": False,
            "hardware_control": False,
            "mqtt_publish": False,
            "modbus_command": False,
            "relay_command": False,
        }
