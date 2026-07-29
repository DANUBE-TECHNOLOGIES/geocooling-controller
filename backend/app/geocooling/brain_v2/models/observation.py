from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from math import isfinite
from typing import Any
from uuid import uuid4


class ObservationValidationError(ValueError):
    """Observation Brain V2 invalide."""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _optional_float(
    value: Any,
    *,
    field_name: str,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float | None:
    if value is None:
        return None

    if isinstance(value, bool):
        raise ObservationValidationError(
            f"{field_name} ne peut pas être un booléen."
        )

    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ObservationValidationError(
            f"{field_name} doit être numérique."
        ) from exc

    if not isfinite(result):
        raise ObservationValidationError(
            f"{field_name} doit être une valeur finie."
        )

    if minimum is not None and result < minimum:
        raise ObservationValidationError(
            f"{field_name} doit être supérieur ou égal à {minimum}."
        )

    if maximum is not None and result > maximum:
        raise ObservationValidationError(
            f"{field_name} doit être inférieur ou égal à {maximum}."
        )

    return result


def _optional_bool(value: Any, *, field_name: str) -> bool | None:
    if value is None:
        return None

    if isinstance(value, bool):
        return value

    if isinstance(value, int) and value in {0, 1}:
        return bool(value)

    if isinstance(value, str):
        normalized = value.strip().lower()

        if normalized in {"true", "on", "yes", "1", "open", "running"}:
            return True

        if normalized in {"false", "off", "no", "0", "closed", "stopped"}:
            return False

    raise ObservationValidationError(
        f"{field_name} doit être un booléen."
    )


@dataclass(slots=True)
class BrainV2Observation:
    observation_id: str = field(
        default_factory=lambda: str(uuid4())
    )
    observed_at: str = field(default_factory=utc_now_iso)
    source: str = "api"

    indoor_temperature_c: float | None = None
    indoor_humidity_percent: float | None = None
    outdoor_temperature_c: float | None = None
    outdoor_humidity_percent: float | None = None

    floor_surface_temperature_c: float | None = None
    floor_supply_temperature_c: float | None = None
    floor_return_temperature_c: float | None = None

    source_inlet_temperature_c: float | None = None
    source_outlet_temperature_c: float | None = None
    flow_rate_l_min: float | None = None

    pump_running: bool | None = None
    valve_open: bool | None = None
    active_cooling: bool | None = None

    electrical_power_w: float | None = None
    thermal_power_w: float | None = None
    cop: float | None = None

    brain_decision: str | None = None
    brain_confidence_percent: float | None = None

    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any],
        *,
        source: str = "api",
    ) -> "BrainV2Observation":
        if not isinstance(payload, dict):
            raise ObservationValidationError(
                "Le corps de l’observation doit être un objet JSON."
            )

        metadata = payload.get("metadata") or {}

        if not isinstance(metadata, dict):
            raise ObservationValidationError(
                "metadata doit être un objet JSON."
            )

        observed_at = str(
            payload.get("observed_at")
            or payload.get("timestamp")
            or utc_now_iso()
        )

        try:
            datetime.fromisoformat(
                observed_at.replace("Z", "+00:00")
            )
        except ValueError as exc:
            raise ObservationValidationError(
                "observed_at doit être une date ISO 8601."
            ) from exc

        observation = cls(
            observation_id=str(
                payload.get("observation_id")
                or uuid4()
            ),
            observed_at=observed_at,
            source=str(payload.get("source") or source),
            indoor_temperature_c=_optional_float(
                payload.get("indoor_temperature_c"),
                field_name="indoor_temperature_c",
                minimum=-30,
                maximum=70,
            ),
            indoor_humidity_percent=_optional_float(
                payload.get("indoor_humidity_percent"),
                field_name="indoor_humidity_percent",
                minimum=0,
                maximum=100,
            ),
            outdoor_temperature_c=_optional_float(
                payload.get("outdoor_temperature_c"),
                field_name="outdoor_temperature_c",
                minimum=-50,
                maximum=70,
            ),
            outdoor_humidity_percent=_optional_float(
                payload.get("outdoor_humidity_percent"),
                field_name="outdoor_humidity_percent",
                minimum=0,
                maximum=100,
            ),
            floor_surface_temperature_c=_optional_float(
                payload.get("floor_surface_temperature_c"),
                field_name="floor_surface_temperature_c",
                minimum=-10,
                maximum=60,
            ),
            floor_supply_temperature_c=_optional_float(
                payload.get("floor_supply_temperature_c"),
                field_name="floor_supply_temperature_c",
                minimum=-10,
                maximum=80,
            ),
            floor_return_temperature_c=_optional_float(
                payload.get("floor_return_temperature_c"),
                field_name="floor_return_temperature_c",
                minimum=-10,
                maximum=80,
            ),
            source_inlet_temperature_c=_optional_float(
                payload.get("source_inlet_temperature_c"),
                field_name="source_inlet_temperature_c",
                minimum=-10,
                maximum=60,
            ),
            source_outlet_temperature_c=_optional_float(
                payload.get("source_outlet_temperature_c"),
                field_name="source_outlet_temperature_c",
                minimum=-10,
                maximum=60,
            ),
            flow_rate_l_min=_optional_float(
                payload.get("flow_rate_l_min"),
                field_name="flow_rate_l_min",
                minimum=0,
                maximum=500,
            ),
            pump_running=_optional_bool(
                payload.get("pump_running"),
                field_name="pump_running",
            ),
            valve_open=_optional_bool(
                payload.get("valve_open"),
                field_name="valve_open",
            ),
            active_cooling=_optional_bool(
                payload.get("active_cooling"),
                field_name="active_cooling",
            ),
            electrical_power_w=_optional_float(
                payload.get("electrical_power_w"),
                field_name="electrical_power_w",
                minimum=0,
                maximum=100000,
            ),
            thermal_power_w=_optional_float(
                payload.get("thermal_power_w"),
                field_name="thermal_power_w",
                minimum=0,
                maximum=200000,
            ),
            cop=_optional_float(
                payload.get("cop"),
                field_name="cop",
                minimum=0,
                maximum=30,
            ),
            brain_decision=(
                str(payload["brain_decision"])
                if payload.get("brain_decision") is not None
                else None
            ),
            brain_confidence_percent=_optional_float(
                payload.get("brain_confidence_percent"),
                field_name="brain_confidence_percent",
                minimum=0,
                maximum=100,
            ),
            metadata=dict(metadata),
        )

        if observation.measurement_count() == 0:
            raise ObservationValidationError(
                "L’observation ne contient aucune mesure exploitable."
            )

        return observation

    def measurement_count(self) -> int:
        excluded = {
            "observation_id",
            "observed_at",
            "source",
            "metadata",
            "brain_decision",
        }

        return sum(
            1
            for key, value in asdict(self).items()
            if key not in excluded and value is not None
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["measurement_count"] = self.measurement_count()
        return payload
