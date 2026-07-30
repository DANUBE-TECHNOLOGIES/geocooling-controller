export type BrainDecision = {
  summary: string;
  confidence: number;
  reasons: string[];
};

export type GeoCoolingMode = "simulation" | "automatic" | "manual" | "unknown";

export type GeoCoolingSnapshot = {
  available: boolean;
  generatedAt: string | null;
  indoorTemperature: number | null;
  humidity: number | null;
  sourceInTemperature: number | null;
  sourceOutTemperature: number | null;
  supplyTemperature: number | null;
  returnTemperature: number | null;
  pumpRunning: boolean;
  valveOpen: boolean;
  mode: GeoCoolingMode;
  safetySafe: boolean | null;
  deviceReady: boolean | null;
  decision: BrainDecision;
};

export type GeoCoolingApiPayload = Record<string, unknown>;
