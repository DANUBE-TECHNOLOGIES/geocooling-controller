export interface SimulationInput {
  indoorTemperature: number;
  humidity: number;

  sourceTemperature: number;

  supplyTemperature: number;
  returnTemperature: number;
}

export interface SimulationResult {

  dewPoint: number;

  condensationMargin: number;

  condensationSafe: boolean;

  coolingDemand: boolean;

  sourceAvailable: boolean;

  estimatedCoolingPowerKw: number;

  estimatedCop: number;

  shouldRun: boolean;

  alarms: string[];
}

function dewPoint(
  temperature: number,
  humidity: number,
): number {

  const a = 17.62;
  const b = 243.12;

  const rh = Math.max(
    1,
    Math.min(100, humidity),
  );

  const gamma =
    Math.log(rh / 100) +
    (a * temperature) /
      (b + temperature);

  return (b * gamma) /
    (a - gamma);
}

export function runSimulation(
  input: SimulationInput,
): SimulationResult {

  const point =
    dewPoint(
      input.indoorTemperature,
      input.humidity,
    );

  const margin =
    input.supplyTemperature -
    point;

  const condensationSafe =
    margin >= 3;

  const coolingDemand =
    input.indoorTemperature >= 25;

  const sourceAvailable =
    input.sourceTemperature <=
    input.indoorTemperature - 3;

  const deltaT =
    input.returnTemperature -
    input.supplyTemperature;

  const estimatedCoolingPowerKw =
    Math.max(
      0,
      deltaT * 1.2,
    );

  const estimatedCop =
    sourceAvailable
      ? 18
      : 4;

  const shouldRun =
    coolingDemand &&
    condensationSafe &&
    sourceAvailable;

  const alarms: string[] = [];

  if (!condensationSafe) {

    alarms.push(
      "Risque de condensation",
    );

  }

  if (!sourceAvailable) {

    alarms.push(
      "Source insuffisamment froide",
    );

  }

  return {

    dewPoint: point,

    condensationMargin: margin,

    condensationSafe,

    coolingDemand,

    sourceAvailable,

    estimatedCoolingPowerKw,

    estimatedCop,

    shouldRun,

    alarms,

  };

}
