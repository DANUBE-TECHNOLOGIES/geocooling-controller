import type {
  GeoCoolingApiPayload,
  GeoCoolingMode,
  GeoCoolingSnapshot,
} from "@/types/geocooling";

const CLIENT_ENDPOINT = "/api/geocooling/snapshot";

function asNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function asBoolean(value: unknown): boolean | null {
  if (typeof value === "boolean") return value;
  if (value === 1 || value === "1" || value === "true" || value === "on") return true;
  if (value === 0 || value === "0" || value === "false" || value === "off") return false;
  return null;
}

function asMode(value: unknown, simulation: unknown): GeoCoolingMode {
  if (asBoolean(simulation) === true) return "simulation";
  const normalized = String(value ?? "").trim().toLowerCase();
  if (normalized.includes("simul")) return "simulation";
  if (normalized.includes("manual")) return "manual";
  if (normalized.includes("auto")) return "automatic";
  return "unknown";
}

function decisionReasons(payload: GeoCoolingApiPayload): string[] {
  const direct = payload.brain_reason;
  if (Array.isArray(direct)) {
    return direct.map(String).map((item) => item.trim()).filter(Boolean);
  }
  if (typeof direct === "string") {
    return direct.split(";").map((item) => item.trim()).filter(Boolean);
  }
  const lastReason = payload.last_reason;
  return typeof lastReason === "string" && lastReason.trim() ? [lastReason.trim()] : [];
}

export function normalizeGeoCoolingSnapshot(payload: GeoCoolingApiPayload): GeoCoolingSnapshot {
  const confidence = asNumber(payload.brain_confidence) ?? 0;
  const decision = String(payload.brain_decision ?? "Décision indisponible").trim();

  return {
    available: asBoolean(payload.available) ?? true,
    generatedAt: typeof payload.generated_at === "string" ? payload.generated_at : null,
    indoorTemperature: asNumber(payload.indoor_temperature_c),
    humidity: asNumber(payload.indoor_humidity_percent),
    sourceInTemperature: asNumber(payload.source_inlet_temperature_c),
    sourceOutTemperature: asNumber(payload.source_outlet_temperature_c),
    supplyTemperature: asNumber(payload.floor_supply_temperature_c),
    returnTemperature: asNumber(payload.floor_return_temperature_c),
    pumpRunning: asBoolean(payload.pump_running) ?? false,
    valveOpen: asBoolean(payload.valve_open) ?? false,
    mode: asMode(payload.mode ?? payload.brain_operating_mode, payload.simulation),
    safetySafe: asBoolean(payload.safety_safe),
    deviceReady: asBoolean(payload.device_ready),
    decision: {
      summary: decision || "Décision indisponible",
      confidence: Math.max(0, Math.min(100, Math.round(confidence))),
      reasons: decisionReasons(payload),
    },
  };
}

export async function fetchGeoCoolingSnapshot(signal?: AbortSignal): Promise<GeoCoolingSnapshot> {
  const response = await fetch(CLIENT_ENDPOINT, {
    cache: "no-store",
    headers: { Accept: "application/json" },
    signal,
  });

  const body = (await response.json().catch(() => null)) as
    | GeoCoolingApiPayload
    | { error?: string }
    | null;

  if (!response.ok) {
    const message = body && typeof body.error === "string"
      ? body.error
      : `API GeoCooling indisponible (${response.status})`;
    throw new Error(message);
  }

  if (!body || typeof body !== "object") {
    throw new Error("Réponse GeoCooling invalide");
  }

  return normalizeGeoCoolingSnapshot(body as GeoCoolingApiPayload);
}
