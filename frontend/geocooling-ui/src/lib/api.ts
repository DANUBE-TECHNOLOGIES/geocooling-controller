import type {
  BrainDecision,
  GeoCoolingMode,
  GeoCoolingSnapshot,
} from "@/types/geocooling";

type BackendSnapshot = {
  available: boolean;

  generated_at: string | null;
  generatedAt?: string | null;

  mode: string;

  device_ready: boolean | null;
  safety_safe: boolean | null;
  safety_reason?: string | null;
  dew_point_c?: number | null;
  condensation_margin_c?: number | null;

  pump_running: boolean;
  valve_open: boolean;

  indoor_temperature_c: number | null;
  indoor_humidity_percent: number | null;
  surface_temperature_c?: number | null;

  source_inlet_temperature_c: number | null;
  source_outlet_temperature_c: number | null;

  floor_supply_temperature_c: number | null;
  floor_return_temperature_c: number | null;
  flow_rate_l_min?: number | null;

  brain_reason?: string;
  brain_confidence?: number;
};

async function request(
  signal?: AbortSignal,
): Promise<BackendSnapshot> {
  const response = await fetch("/api/geocooling/snapshot", {
    cache: "no-store",
    signal,
    headers: {
      Accept: "application/json",
    },
  });

  if (!response.ok) {
    throw new Error(await response.text());
  }

  return response.json() as Promise<BackendSnapshot>;
}

function mapMode(mode: string): GeoCoolingMode {
  switch ((mode ?? "").toUpperCase()) {
    case "SIMULATION":
      return "simulation";

    case "AUTOMATIC":
    case "AUTO":
      return "automatic";

    case "MANUAL":
      return "manual";

    default:
      return "unknown";
  }
}

export async function fetchGeoCoolingSnapshot(
  signal?: AbortSignal,
): Promise<GeoCoolingSnapshot> {

  const raw = await request(signal);

  const decision: BrainDecision = {
    summary: raw.brain_reason ?? "",
    confidence: raw.brain_confidence ?? 0,
    reasons: raw.brain_reason
      ? raw.brain_reason
          .split(";")
          .map((v) => v.trim())
          .filter(Boolean)
      : [],
  };

  return {
    available: raw.available,

    generatedAt:
      raw.generated_at ??
      raw.generatedAt ??
      null,

    indoorTemperature:
      raw.indoor_temperature_c,

    humidity:
      raw.indoor_humidity_percent,

    surfaceTemperature:
      raw.surface_temperature_c ?? null,

    sourceInTemperature:
      raw.source_inlet_temperature_c,

    sourceOutTemperature:
      raw.source_outlet_temperature_c,

    supplyTemperature:
      raw.floor_supply_temperature_c,

    returnTemperature:
      raw.floor_return_temperature_c,

    flowRate:
      raw.flow_rate_l_min ?? null,

    dewPoint:
      raw.dew_point_c ?? null,

    condensationMargin:
      raw.condensation_margin_c ?? null,

    pumpRunning:
      raw.pump_running,

    valveOpen:
      raw.valve_open,

    mode:
      mapMode(raw.mode),

    safetySafe:
      raw.safety_safe,

    safetyReason:
      raw.safety_reason ?? null,

    deviceReady:
      raw.device_ready,

    decision,
  };
}