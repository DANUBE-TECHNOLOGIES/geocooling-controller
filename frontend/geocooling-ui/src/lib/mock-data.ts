import type { GeoCoolingSnapshot } from "@/types/geocooling";

export const mockSnapshot: GeoCoolingSnapshot = {
  indoorTemperature: 26.1,
  humidity: 54,
  sourceInTemperature: 12.3,
  sourceOutTemperature: 15.0,
  supplyTemperature: 18.0,
  returnTemperature: 20.5,
  pumpRunning: false,
  valveOpen: false,
  mode: "simulation",
  decision: {
    summary: "Le Brain poursuit l’apprentissage thermique avant d’autoriser le refroidissement.",
    confidence: 92,
    reasons: [
      "Température intérieure supérieure à la consigne de confort",
      "Marge de condensation actuellement compatible",
      "Installation maintenue en simulation sécurisée",
    ],
  },
};
