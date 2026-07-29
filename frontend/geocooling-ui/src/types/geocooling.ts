export type BrainDecision = {
  summary: string;
  confidence: number;
  reasons: string[];
};

export type GeoCoolingSnapshot = {
  indoorTemperature: number;
  humidity: number;
  sourceInTemperature: number;
  sourceOutTemperature: number;
  supplyTemperature: number;
  returnTemperature: number;
  pumpRunning: boolean;
  valveOpen: boolean;
  mode: "simulation" | "automatic" | "manual";
  decision: BrainDecision;
};
