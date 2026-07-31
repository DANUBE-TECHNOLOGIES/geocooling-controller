import type {
  BrainDecision,
  GeoCoolingApiPayload,
  GeoCoolingMode,
  GeoCoolingSnapshot,
} from "@/types/geocooling";

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value)
    ? value
    : null;
}

function asBoolean(value: unknown): boolean | null {
  return typeof value === "boolean" ? value : null;
}

function asString(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0
    ? value.trim()
    : null;
}

function normalizeMode(value: unknown): GeoCoolingMode {
  switch (String(value ?? "").trim().toLowerCase()) {
    case "manual":
    case "manuel":
      return "manual";

    case "automatic":
    case "auto":
    case "automatique":
      return "automatic";

    case "simulation":
      return "simulation";

    default:
      return "unknown";
  }
}

function normalizeDecision(raw: GeoCoolingApiPayload): BrainDecision {
  const decisionCode =
    asString(raw.brain_decision) ??
    asString(raw.decision);

  const explanation =
    asString(raw.brain_reason) ??
    asString(raw.last_reason);

  const summary =
    explanation ??
    decisionCode ??
    "Aucune décision disponible";

  const reasons = explanation
    ? explanation
        .split(";")
        .map((reason) => reason.trim())
        .filter(Boolean)
    : [];

  return {
    summary,
    confidence:
      asNumber(raw.brain_confidence) ??
      asNumber(raw.confidence) ??
      0,
    reasons,
  };
}

export function normalizeSnapshot(input: unknown): GeoCoolingSnapshot {
  const raw: GeoCoolingApiPayload =
    typeof input === "object" && input !== null
      ? (input as GeoCoolingApiPayload)
      : {};

  return {
    available: Boolean(raw.available),

    generatedAt:
      asString(raw.generated_at) ??
      asString(raw.generatedAt),

    indoorTemperature:
      asNumber(raw.indoor_temperature_c) ??
      asNumber(raw.indoorTemperature),

    humidity:
      asNumber(raw.indoor_humidity_percent) ??
      asNumber(raw.humidity),

    sourceInTemperature:
      asNumber(raw.source_inlet_temperature_c) ??
      asNumber(raw.sourceInTemperature),

    sourceOutTemperature:
      asNumber(raw.source_outlet_temperature_c) ??
      asNumber(raw.sourceOutTemperature),

    supplyTemperature:
      asNumber(raw.floor_supply_temperature_c) ??
      asNumber(raw.supplyTemperature),

    returnTemperature:
      asNumber(raw.floor_return_temperature_c) ??
      asNumber(raw.returnTemperature),

    pumpRunning:
      asBoolean(raw.pump_running) ??
      asBoolean(raw.pumpRunning) ??
      false,

    valveOpen:
      asBoolean(raw.valve_open) ??
      asBoolean(raw.valveOpen) ??
      false,

    mode: normalizeMode(raw.mode),

    safetySafe:
      asBoolean(raw.safety_safe) ??
      asBoolean(raw.safetySafe),

    deviceReady:
      asBoolean(raw.device_ready) ??
      asBoolean(raw.deviceReady),

    decision: normalizeDecision(raw),
  };
}
