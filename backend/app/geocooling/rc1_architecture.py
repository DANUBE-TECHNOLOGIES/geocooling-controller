from __future__ import annotations
import importlib.util
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Final

@dataclass(frozen=True, slots=True)
class ComponentContract:
    role: str
    module: str
    symbol: str | None
    required: bool
    description: str

CANONICAL_PIPELINE: Final[tuple[ComponentContract, ...]] = (
    ComponentContract("sensors","app.building.service","BuildingStateService",True,"Building measurements"),
    ComponentContract("historian","app.geocooling.brain_memory","BrainMemory",True,"Operational memory"),
    ComponentContract("weather","app.weather_service","WeatherService",True,"Canonical weather service"),
    ComponentContract("learning","app.geocooling.adaptive_model","AdaptiveThermalModel",True,"Adaptive building model"),
    ComponentContract("thermal_engine","app.geocooling.thermal",None,True,"Thermal engine"),
    ComponentContract("prediction","app.geocooling.predictor",None,True,"Operational predictor"),
    ComponentContract("brain","app.geocooling.brain","GeoCoolingBrain",True,"Operational decision authority"),
    ComponentContract("safety","app.geocooling.controller_safety_gate",None,True,"Final safety gate"),
    ComponentContract("controller","app.geocooling.controller",None,True,"Operational controller"),
    ComponentContract("hardware","app.geocooling.waveshare_modbus_driver",None,True,"Waveshare Modbus driver"),
)
LEGACY_OR_ADVISORY_COMPONENTS: Final[tuple[ComponentContract, ...]] = (
    ComponentContract("advisory_brain_v2","app.geocooling.brain_v2",None,False,"Advisory subsystem"),
    ComponentContract("experimental_brain_v4","app.geocooling.brain_v4",None,False,"Experimental generation"),
    ComponentContract("experimental_brain_v5","app.geocooling.brain_v5",None,False,"Experimental generation"),
    ComponentContract("weather_h024_candidate","app.geocooling.weather.service","WeatherService",False,"Candidate weather service"),
)

def _available(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, AttributeError, ValueError):
        return False

def architecture_status() -> dict[str, object]:
    canonical=[{**asdict(c),"available":_available(c.module)} for c in CANONICAL_PIPELINE]
    legacy=[{**asdict(c),"available":_available(c.module)} for c in LEGACY_OR_ADVISORY_COMPONENTS]
    missing=[x["role"] for x in canonical if x["required"] and not x["available"]]
    return {
        "schema":"geocooling.rc1.architecture.v1",
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "authority":{
            "brain":"app.geocooling.brain.GeoCoolingBrain",
            "controller":"app.geocooling.controller",
            "hardware":"app.geocooling.waveshare_modbus_driver",
            "weather":"app.weather_service.WeatherService",
        },
        "pipeline":canonical,
        "legacy_or_advisory":legacy,
        "missing_required":missing,
        "ready":not missing,
        "safety":{"side_effect_free":True,"hardware_write":False,"mqtt_publish":False,"database_write":False},
    }
