"use client";

import Link from "next/link";
import {
  useEffect,
  useMemo,
  useState,
} from "react";

import { AppShell } from "@/components/layout/AppShell";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useGeoCooling } from "@/hooks/useGeoCooling";
import type { GeoCoolingSnapshot } from "@/types/geocooling";

type TwinMode =
  | "realtime"
  | "simulation";

type TwinScenario = {
  indoorTemperature: number;
  humidity: number;
  sourceInTemperature: number;
  sourceOutTemperature: number;
  supplyTemperature: number;
  returnTemperature: number;
  valveOpen: boolean;
  pumpRunning: boolean;
  safetySafe: boolean;
};

type TwinResult = {
  dewPoint: number;
  condensationMargin: number;
  sourceDelta: number;
  floorDelta: number;
  projectedIndoorTemperature: number;
  thermalEffect: number;
  sourceFlow: boolean;
  floorFlow: boolean;
  safe: boolean;
  coherent: boolean;
};

type MetricTone =
  | "good"
  | "warning"
  | "critical"
  | "neutral";

type ScenarioPresetKey =
  | "optimal"
  | "heatwave"
  | "humid"
  | "safety-stop";

type ScenarioPreset = {
  key: ScenarioPresetKey;
  label: string;
  description: string;
  scenario: TwinScenario;
};

type ProjectionPoint = {
  hour: number;
  indoorTemperature: number;
  dewPoint: number;
  condensationMargin: number;
  thermalEffect: number;
};

type ComparisonMetric = {
  label: string;
  unit: string;
  realtime: number | null;
  simulation: number;
  difference: number | null;
};

function validNumber(
  value: number | null | undefined,
): value is number {
  return (
    typeof value === "number" &&
    Number.isFinite(value)
  );
}

function numberOr(
  value: number | null | undefined,
  fallback: number,
): number {
  return validNumber(value)
    ? value
    : fallback;
}

function calculateDewPoint(
  temperature: number,
  humidity: number,
): number {
  const boundedHumidity =
    Math.min(
      100,
      Math.max(1, humidity),
    );

  const a = 17.62;
  const b = 243.12;

  const gamma =
    Math.log(
      boundedHumidity / 100,
    ) +
    (
      a * temperature
    ) /
      (
        b + temperature
      );

  return (
    b * gamma
  ) /
    (
      a - gamma
    );
}

function calculateTwin(
  scenario: TwinScenario,
): TwinResult {
  const dewPoint =
    calculateDewPoint(
      scenario.indoorTemperature,
      scenario.humidity,
    );

  const condensationMargin =
    scenario.supplyTemperature -
    dewPoint;

  const sourceDelta =
    scenario.sourceOutTemperature -
    scenario.sourceInTemperature;

  const floorDelta =
    scenario.returnTemperature -
    scenario.supplyTemperature;

  const sourceFlow =
    scenario.valveOpen &&
    scenario.safetySafe;

  const floorFlow =
    scenario.pumpRunning &&
    scenario.valveOpen &&
    scenario.safetySafe;

  const hydraulicEffect =
    floorFlow
      ? Math.max(
          0,
          Math.min(
            2.5,
            Math.abs(
              floorDelta,
            ) *
              0.42 +
              Math.max(
                0,
                scenario.indoorTemperature -
                  scenario.supplyTemperature,
              ) *
                0.08,
          ),
        )
      : 0;

  return {
    dewPoint,
    condensationMargin,
    sourceDelta,
    floorDelta,

    projectedIndoorTemperature:
      scenario.indoorTemperature -
      hydraulicEffect,

    thermalEffect:
      hydraulicEffect,

    sourceFlow,
    floorFlow,

    safe:
      scenario.safetySafe &&
      condensationMargin >= 3,

    coherent:
      floorDelta >= -0.5 &&
      floorDelta <= 6 &&
      (
        !scenario.pumpRunning ||
        scenario.valveOpen
      ),
  };
}

function buildScenario(
  snapshot: GeoCoolingSnapshot | null,
): TwinScenario {
  return {
    indoorTemperature:
      numberOr(
        snapshot?.indoorTemperature,
        25,
      ),

    humidity:
      numberOr(
        snapshot?.humidity,
        55,
      ),

    sourceInTemperature:
      numberOr(
        snapshot?.sourceInTemperature,
        13,
      ),

    sourceOutTemperature:
      numberOr(
        snapshot?.sourceOutTemperature,
        15,
      ),

    supplyTemperature:
      numberOr(
        snapshot?.supplyTemperature,
        18,
      ),

    returnTemperature:
      numberOr(
        snapshot?.returnTemperature,
        20,
      ),

    valveOpen:
      snapshot?.valveOpen ??
      false,

    pumpRunning:
      snapshot?.pumpRunning ??
      false,

    safetySafe:
      snapshot?.safetySafe !==
      false,
  };
}

function formatTemperature(
  value: number,
): string {
  return `${value.toFixed(1)} °C`;
}

const PROJECTION_WIDTH = 1_000;
const PROJECTION_HEIGHT = 240;

const SCENARIO_PRESETS: ScenarioPreset[] = [
  {
    key: "optimal",
    label: "Fonctionnement optimal",
    description:
      "Rafraîchissement actif avec marge de condensation confortable.",
    scenario: {
      indoorTemperature: 26,
      humidity: 52,
      sourceInTemperature: 12.5,
      sourceOutTemperature: 15,
      supplyTemperature: 18,
      returnTemperature: 20.5,
      valveOpen: true,
      pumpRunning: true,
      safetySafe: true,
    },
  },
  {
    key: "heatwave",
    label: "Épisode caniculaire",
    description:
      "Température intérieure élevée et sollicitation maximale du plancher.",
    scenario: {
      indoorTemperature: 30.5,
      humidity: 48,
      sourceInTemperature: 13.5,
      sourceOutTemperature: 16.5,
      supplyTemperature: 18,
      returnTemperature: 22.5,
      valveOpen: true,
      pumpRunning: true,
      safetySafe: true,
    },
  },
  {
    key: "humid",
    label: "Forte humidité",
    description:
      "Conditions proches du point de rosée avec risque de condensation.",
    scenario: {
      indoorTemperature: 26,
      humidity: 78,
      sourceInTemperature: 13,
      sourceOutTemperature: 15.5,
      supplyTemperature: 18,
      returnTemperature: 20,
      valveOpen: true,
      pumpRunning: true,
      safetySafe: true,
    },
  },
  {
    key: "safety-stop",
    label: "Arrêt sécurité",
    description:
      "Simulation d’un blocage de la chaîne hydraulique.",
    scenario: {
      indoorTemperature: 27,
      humidity: 60,
      sourceInTemperature: 13,
      sourceOutTemperature: 13,
      supplyTemperature: 22,
      returnTemperature: 22,
      valveOpen: false,
      pumpRunning: false,
      safetySafe: false,
    },
  },
];

function clamp(
  value: number,
  minimum: number,
  maximum: number,
): number {
  return Math.min(
    maximum,
    Math.max(minimum, value),
  );
}

function calculateProjection(
  scenario: TwinScenario,
  hours: number,
): ProjectionPoint[] {
  const points: ProjectionPoint[] = [];

  let indoorTemperature =
    scenario.indoorTemperature;

  for (
    let hour = 0;
    hour <= hours;
    hour += 1
  ) {
    const hourlyScenario: TwinScenario = {
      ...scenario,
      indoorTemperature,
    };

    const result =
      calculateTwin(
        hourlyScenario,
      );

    points.push({
      hour,
      indoorTemperature,
      dewPoint:
        result.dewPoint,
      condensationMargin:
        result.condensationMargin,
      thermalEffect:
        result.thermalEffect,
    });

    const coolingPerHour =
      result.floorFlow
        ? clamp(
            result.thermalEffect *
              0.22,
            0,
            0.55,
          )
        : 0;

    const naturalDrift =
      result.floorFlow
        ? 0.06
        : 0.22;

    indoorTemperature =
      indoorTemperature -
      coolingPerHour +
      naturalDrift;

    indoorTemperature =
      clamp(
        indoorTemperature,
        16,
        38,
      );
  }

  return points;
}

function projectionRange(
  points: ProjectionPoint[],
): {
  minimum: number;
  maximum: number;
} {
  const values =
    points.flatMap(
      (point) => [
        point.indoorTemperature,
        point.dewPoint,
      ],
    );

  if (values.length === 0) {
    return {
      minimum: 10,
      maximum: 30,
    };
  }

  const rawMinimum =
    Math.min(...values);

  const rawMaximum =
    Math.max(...values);

  return {
    minimum:
      Math.floor(
        rawMinimum - 1,
      ),

    maximum:
      Math.ceil(
        rawMaximum + 1,
      ),
  };
}

function projectionPath(
  points: ProjectionPoint[],
  key:
    | "indoorTemperature"
    | "dewPoint",
  minimum: number,
  maximum: number,
): string {
  const span =
    Math.max(
      0.1,
      maximum - minimum,
    );

  return points
    .map((point, index) => {
      const x =
        points.length <= 1
          ? 0
          : (
              index /
              (
                points.length -
                1
              )
            ) *
            PROJECTION_WIDTH;

      const value =
        point[key];

      const y =
        PROJECTION_HEIGHT -
        (
          (
            value -
            minimum
          ) /
          span
        ) *
          PROJECTION_HEIGHT;

      return `${
        index === 0
          ? "M"
          : "L"
      } ${x.toFixed(
        2,
      )} ${y.toFixed(
        2,
      )}`;
    })
    .join(" ");
}

function downloadJson(
  payload: unknown,
  filename: string,
): void {
  const content =
    JSON.stringify(
      payload,
      null,
      2,
    );

  const blob =
    new Blob(
      [content],
      {
        type:
          "application/json;charset=utf-8",
      },
    );

  const url =
    URL.createObjectURL(
      blob,
    );

  const anchor =
    document.createElement(
      "a",
    );

  anchor.href = url;
  anchor.download =
    filename;

  anchor.click();

  URL.revokeObjectURL(
    url,
  );
}

function metricTone(
  value: number,
  warningThreshold: number,
  criticalThreshold: number,
  inverse = false,
): MetricTone {
  if (inverse) {
    if (
      value <= criticalThreshold
    ) {
      return "critical";
    }

    if (
      value <= warningThreshold
    ) {
      return "warning";
    }

    return "good";
  }

  if (
    value >= criticalThreshold
  ) {
    return "critical";
  }

  if (
    value >= warningThreshold
  ) {
    return "warning";
  }

  return "good";
}

export default function DigitalTwinPage() {
  const {
    snapshot,
    loading,
    refreshing,
    error,
    lastUpdate,
    responseTime,
    refresh,
  } = useGeoCooling();

  const connected =
    Boolean(
      snapshot &&
      !error,
    );

  const [mode, setMode] =
    useState<TwinMode>(
      "realtime",
    );

  const [
    simulation,
    setSimulation,
  ] =
    useState<TwinScenario>(
      () =>
        buildScenario(null),
    );

  const [
    selectedPreset,
    setSelectedPreset,
  ] =
    useState<ScenarioPresetKey | null>(
      null,
    );

  const [
    projectionHours,
    setProjectionHours,
  ] =
    useState(12);

  useEffect(() => {
    if (
      !snapshot ||
      mode !== "realtime"
    ) {
      return;
    }

    setSimulation(
      buildScenario(snapshot),
    );
  }, [
    snapshot,
    mode,
  ]);

  const scenario =
    mode === "realtime"
      ? buildScenario(snapshot)
      : simulation;

  const result =
    useMemo(
      () =>
        calculateTwin(
          scenario,
        ),
      [scenario],
    );

  const updateNumber = (
    key:
      | "indoorTemperature"
      | "humidity"
      | "sourceInTemperature"
      | "sourceOutTemperature"
      | "supplyTemperature"
      | "returnTemperature",
    value: string,
  ) => {
    const parsed =
      Number(value);

    if (
      !Number.isFinite(parsed)
    ) {
      return;
    }

    setSimulation(
      (current) => ({
        ...current,
        [key]: parsed,
      }),
    );

    setSelectedPreset(null);
  };

  const updateBoolean = (
    key:
      | "valveOpen"
      | "pumpRunning"
      | "safetySafe",
    value: boolean,
  ) => {
    setSimulation(
      (current) => ({
        ...current,
        [key]: value,
      }),
    );

    setSelectedPreset(null);
  };

  const loadRealtimeIntoSimulation =
    () => {
      setSimulation(
        buildScenario(snapshot),
      );

      setSelectedPreset(null);

      setMode(
        "simulation",
      );
    };

  const applyPreset = (
    preset: ScenarioPreset,
  ) => {
    setSimulation({
      ...preset.scenario,
    });

    setSelectedPreset(
      preset.key,
    );

    setMode(
      "simulation",
    );
  };

  const processTone:
    MetricTone =
    !result.safe
      ? "critical"
      : !result.coherent
        ? "warning"
        : result.floorFlow
          ? "good"
          : "neutral";

  const tankFill =
    Math.min(
      88,
      Math.max(
        28,
        72 -
          (
            scenario.supplyTemperature -
            16
          ) *
            3,
      ),
    );

  const projection =
    useMemo(
      () =>
        calculateProjection(
          scenario,
          projectionHours,
        ),
      [
        scenario,
        projectionHours,
      ],
    );

  const projectionTemperatureRange =
    useMemo(
      () =>
        projectionRange(
          projection,
        ),
      [projection],
    );

  const indoorProjectionPath =
    useMemo(
      () =>
        projectionPath(
          projection,
          "indoorTemperature",
          projectionTemperatureRange.minimum,
          projectionTemperatureRange.maximum,
        ),
      [
        projection,
        projectionTemperatureRange,
      ],
    );

  const dewPointProjectionPath =
    useMemo(
      () =>
        projectionPath(
          projection,
          "dewPoint",
          projectionTemperatureRange.minimum,
          projectionTemperatureRange.maximum,
        ),
      [
        projection,
        projectionTemperatureRange,
      ],
    );

  const finalProjection =
    projection.at(-1) ??
    null;

  const minimumCondensationMargin =
    projection.length === 0
      ? null
      : Math.min(
          ...projection.map(
            (point) =>
              point.condensationMargin,
          ),
        );

  const riskHours =
    projection.filter(
      (point) =>
        point.condensationMargin <
        3,
    ).length;

  const realtimeScenario =
    buildScenario(snapshot);

  const comparisonMetrics:
    ComparisonMetric[] = [
      {
        label:
          "Température intérieure",
        unit: "°C",
        realtime:
          snapshot
            ? realtimeScenario.indoorTemperature
            : null,
        simulation:
          simulation.indoorTemperature,
        difference:
          snapshot
            ? simulation.indoorTemperature -
              realtimeScenario.indoorTemperature
            : null,
      },
      {
        label:
          "Humidité",
        unit: "%",
        realtime:
          snapshot
            ? realtimeScenario.humidity
            : null,
        simulation:
          simulation.humidity,
        difference:
          snapshot
            ? simulation.humidity -
              realtimeScenario.humidity
            : null,
      },
      {
        label:
          "Départ plancher",
        unit: "°C",
        realtime:
          snapshot
            ? realtimeScenario.supplyTemperature
            : null,
        simulation:
          simulation.supplyTemperature,
        difference:
          snapshot
            ? simulation.supplyTemperature -
              realtimeScenario.supplyTemperature
            : null,
      },
      {
        label:
          "Retour plancher",
        unit: "°C",
        realtime:
          snapshot
            ? realtimeScenario.returnTemperature
            : null,
        simulation:
          simulation.returnTemperature,
        difference:
          snapshot
            ? simulation.returnTemperature -
              realtimeScenario.returnTemperature
            : null,
      },
    ];

  const exportScenario = () => {
    downloadJson(
      {
        exportedAt:
          new Date().toISOString(),

        mode,

        selectedPreset,

        projectionHours,

        scenario,

        result,

        projection,

        comparison:
          comparisonMetrics,
      },
      `geocooling-digital-twin-${new Date()
        .toISOString()
        .replaceAll(
          ":",
          "-",
        )}.json`,
    );
  };

  return (
    <AppShell
      connected={connected}
      mode={String(
        snapshot?.mode ??
        "INCONNU",
      )}
      refreshing={refreshing}
      lastUpdate={lastUpdate}
      generatedAt={
        snapshot?.generatedAt
      }
      responseTime={responseTime}
      onRefresh={() => {
        void refresh();
      }}
    >
      <section className="gc-page-header">
        <div>
          <p className="gc-page-header__eyebrow">
            DIGITAL TWIN PROCESS
          </p>

          <h2>
            Jumeau numérique animé
          </h2>

          <p>
            Représentation dynamique de la chaîne
            hydraulique, de l’équilibre thermique et
            des conditions de sécurité GeoCooling.
          </p>
        </div>

        <div className="gc-page-header__actions">
          <Link
            href="/"
            className="gc-page-link"
          >
            ← Dashboard
          </Link>

          <StatusBadge
            label={
              mode === "realtime"
                ? connected
                  ? "TEMPS RÉEL"
                  : "SOURCE HORS LIGNE"
                : "SIMULATION LOCALE"
            }
            tone={
              mode === "simulation"
                ? "info"
                : connected
                  ? "success"
                  : "danger"
            }
            pulse={
              mode === "realtime" &&
              connected
            }
          />
        </div>
      </section>

      <section className="gc-dt-modebar">
        <div>
          <button
            type="button"
            className={
              mode === "realtime"
                ? "is-active"
                : ""
            }
            onClick={() =>
              setMode(
                "realtime",
              )
            }
          >
            <span>●</span>

            Temps réel
          </button>

          <button
            type="button"
            className={
              mode === "simulation"
                ? "is-active"
                : ""
            }
            onClick={() =>
              setMode(
                "simulation",
              )
            }
          >
            <span>◇</span>

            Simulation
          </button>
        </div>

        <section>
          <strong>
            {mode === "realtime"
              ? "Le synoptique suit le snapshot du contrôleur."
              : "Les paramètres sont calculés uniquement dans le navigateur."}
          </strong>

          <small>
            Aucune commande MQTT, Modbus ou relais
            n’est envoyée depuis cette page.
          </small>
        </section>

        <button
          type="button"
          onClick={
            loadRealtimeIntoSimulation
          }
          disabled={!snapshot}
        >
          Copier le réel
        </button>
      </section>

      {loading && !snapshot ? (
        <section className="gc-loading-state">
          <div className="gc-loading-spinner" />

          <div>
            <strong>
              Chargement du jumeau numérique…
            </strong>

            <span>
              Lecture du premier snapshot.
            </span>
          </div>
        </section>
      ) : null}

      <section className="gc-dt-scenario-lab">
        <header>
          <div>
            <p className="gc-page-header__eyebrow">
              SCENARIO LAB
            </p>

            <h3>
              Bibliothèque de scénarios
            </h3>
          </div>

          <button
            type="button"
            onClick={exportScenario}
          >
            Exporter le scénario
          </button>
        </header>

        <div>
          {SCENARIO_PRESETS.map(
            (preset) => (
              <button
                key={preset.key}
                type="button"
                className={
                  selectedPreset ===
                  preset.key
                    ? "is-active"
                    : ""
                }
                onClick={() =>
                  applyPreset(
                    preset,
                  )
                }
              >
                <span>
                  {preset.key ===
                  "optimal"
                    ? "✓"
                    : preset.key ===
                        "heatwave"
                      ? "☀"
                      : preset.key ===
                          "humid"
                        ? "%"
                        : "!"}
                </span>

                <div>
                  <strong>
                    {preset.label}
                  </strong>

                  <small>
                    {preset.description}
                  </small>
                </div>
              </button>
            ),
          )}
        </div>
      </section>

      <section className="gc-dt-overview">
        <article
          className={`gc-dt-state is-${processTone}`}
        >
          <div>
            <span />
          </div>

          <section>
            <span>
              ÉTAT DU PROCESS
            </span>

            <strong>
              {!scenario.safetySafe
                ? "Chaîne bloquée par la sécurité"
                : !result.coherent
                  ? "Configuration hydraulique incohérente"
                  : result.floorFlow
                    ? "Rafraîchissement hydraulique actif"
                    : result.sourceFlow
                      ? "Source ouverte, circulateur arrêté"
                      : "Installation en veille"}
            </strong>
          </section>
        </article>

        <article>
          <span>
            AMBIANCE
          </span>

          <strong>
            {formatTemperature(
              scenario.indoorTemperature,
            )}
          </strong>

          <small>
            Humidité{" "}
            {scenario.humidity.toFixed(
              0,
            )} %
          </small>
        </article>

        <article>
          <span>
            MARGE CONDENSATION
          </span>

          <strong
            className={`is-${metricTone(
              result.condensationMargin,
              3,
              2,
              true,
            )}`}
          >
            {formatTemperature(
              result.condensationMargin,
            )}
          </strong>

          <small>
            Départ moins point de rosée
          </small>
        </article>

        <article>
          <span>
            ΔT PLANCHER
          </span>

          <strong>
            {formatTemperature(
              result.floorDelta,
            )}
          </strong>

          <small>
            Retour moins départ
          </small>
        </article>

        <article>
          <span>
            EFFET ESTIMÉ
          </span>

          <strong
            className={
              result.floorFlow
                ? "is-good"
                : "is-neutral"
            }
          >
            −{result.thermalEffect.toFixed(
              1,
            )} °C
          </strong>

          <small>
            Modèle local simplifié
          </small>
        </article>
      </section>

      <section
        className={`gc-dt-process is-${processTone}`}
      >
        <header>
          <div>
            <p className="gc-page-header__eyebrow">
              SYNOPTIQUE ANIMÉ
            </p>

            <h3>
              Installation hydraulique complète
            </h3>
          </div>

          <div className="gc-dt-process__legend">
            <span className="is-source">
              <i />
              Circuit source
            </span>

            <span className="is-floor">
              <i />
              Circuit plancher
            </span>

            <span className="is-idle">
              <i />
              Inactif
            </span>
          </div>
        </header>

        <div className="gc-dt-process__canvas">
          <svg
            viewBox="0 0 1400 620"
            role="img"
            aria-labelledby="digital-twin-title digital-twin-description"
          >
            <title id="digital-twin-title">
              Jumeau numérique hydraulique GeoCooling
            </title>

            <desc id="digital-twin-description">
              Nappe, échangeur, vanne, ballon tampon,
              circulateur, plancher rafraîchissant et
              ambiance intérieure.
            </desc>

            <defs>
              <linearGradient
                id="dtTankGradient"
                x1="0"
                y1="0"
                x2="0"
                y2="1"
              >
                <stop
                  offset="0%"
                  stopColor="rgba(84,216,255,0.75)"
                />

                <stop
                  offset="100%"
                  stopColor="rgba(77,163,255,0.22)"
                />
              </linearGradient>

              <linearGradient
                id="dtRoomGradient"
                x1="0"
                y1="0"
                x2="0"
                y2="1"
              >
                <stop
                  offset="0%"
                  stopColor="rgba(244,201,93,0.18)"
                />

                <stop
                  offset="100%"
                  stopColor="rgba(84,216,255,0.08)"
                />
              </linearGradient>

              <filter
                id="dtGlow"
                x="-40%"
                y="-40%"
                width="180%"
                height="180%"
              >
                <feGaussianBlur
                  stdDeviation="5"
                  result="blur"
                />

                <feMerge>
                  <feMergeNode
                    in="blur"
                  />

                  <feMergeNode
                    in="SourceGraphic"
                  />
                </feMerge>
              </filter>
            </defs>

            <g className="gc-dt-grid">
              <path d="M0 100 H1400" />
              <path d="M0 200 H1400" />
              <path d="M0 300 H1400" />
              <path d="M0 400 H1400" />
              <path d="M0 500 H1400" />

              <path d="M200 0 V620" />
              <path d="M400 0 V620" />
              <path d="M600 0 V620" />
              <path d="M800 0 V620" />
              <path d="M1000 0 V620" />
              <path d="M1200 0 V620" />
            </g>

            <path
              className={
                result.sourceFlow
                  ? "gc-dt-pipe gc-dt-pipe-source is-flowing"
                  : "gc-dt-pipe is-idle"
              }
              d="M165 300 H290"
            />

            <path
              className={
                result.sourceFlow
                  ? "gc-dt-pipe gc-dt-pipe-source is-flowing"
                  : "gc-dt-pipe is-idle"
              }
              d="M430 300 H535"
            />

            <path
              className={
                result.sourceFlow
                  ? "gc-dt-pipe gc-dt-pipe-source is-flowing"
                  : "gc-dt-pipe is-idle"
              }
              d="M655 300 H760"
            />

            <path
              className={
                result.floorFlow
                  ? "gc-dt-pipe gc-dt-pipe-floor is-flowing"
                  : "gc-dt-pipe is-idle"
              }
              d="M910 300 H1035"
            />

            <path
              className={
                result.floorFlow
                  ? "gc-dt-pipe gc-dt-pipe-floor is-flowing"
                  : "gc-dt-pipe is-idle"
              }
              d="M1135 300 H1225"
            />

            <path
              className={
                result.floorFlow
                  ? "gc-dt-return-pipe is-flowing"
                  : "gc-dt-return-pipe is-idle"
              }
              d="M1320 430 H840 V390"
            />

            <g className="gc-dt-source">
              <rect
                x="35"
                y="215"
                width="130"
                height="170"
                rx="30"
              />

              <path
                d="M60 305 C78 278 94 330 118 298 C132 281 142 286 150 297"
              />

              <path
                d="M60 330 C78 303 94 355 118 323 C132 306 142 311 150 322"
              />

              <text
                x="100"
                y="250"
                textAnchor="middle"
              >
                NAPPE
              </text>

              <text
                x="100"
                y="270"
                textAnchor="middle"
                className="gc-dt-svg-small"
              >
                SOURCE
              </text>
            </g>

            <g className="gc-dt-exchanger">
              <rect
                x="290"
                y="205"
                width="140"
                height="190"
                rx="28"
              />

              <path d="M325 250 L395 350" />
              <path d="M395 250 L325 350" />

              <path d="M320 275 H400" />
              <path d="M320 325 H400" />

              <text
                x="360"
                y="235"
                textAnchor="middle"
              >
                ÉCHANGEUR
              </text>

              <text
                x="360"
                y="375"
                textAnchor="middle"
                className="gc-dt-svg-small"
              >
                À PLAQUES
              </text>
            </g>

            <g
              className={`gc-dt-valve ${
                scenario.valveOpen
                  ? "is-open"
                  : "is-closed"
              }`}
            >
              <rect
                x="535"
                y="230"
                width="120"
                height="140"
                rx="24"
              />

              <path d="M565 278 L595 300 L565 322 Z" />
              <path d="M625 278 L595 300 L625 322 Z" />

              <line
                x1="595"
                y1="268"
                x2="595"
                y2="240"
              />

              <circle
                cx="595"
                cy="230"
                r="12"
              />

              <text
                x="595"
                y="350"
                textAnchor="middle"
              >
                VANNE
              </text>
            </g>

            <g className="gc-dt-tank">
              <rect
                x="760"
                y="180"
                width="150"
                height="240"
                rx="38"
              />

              <clipPath id="dtTankClip">
                <rect
                  x="774"
                  y="194"
                  width="122"
                  height="212"
                  rx="26"
                />
              </clipPath>

              <rect
                className={
                  result.floorFlow
                    ? "gc-dt-tank-fluid is-active"
                    : "gc-dt-tank-fluid"
                }
                x="774"
                y={
                  194 +
                  212 *
                    (
                      1 -
                      tankFill / 100
                    )
                }
                width="122"
                height={
                  212 *
                  (
                    tankFill / 100
                  )
                }
                clipPath="url(#dtTankClip)"
                fill="url(#dtTankGradient)"
              />

              <path
                className="gc-dt-tank-wave"
                d={`M774 ${
                  194 +
                  212 *
                    (
                      1 -
                      tankFill / 100
                    )
                } Q805 ${
                  184 +
                  212 *
                    (
                      1 -
                      tankFill / 100
                    )
                } 835 ${
                  194 +
                  212 *
                    (
                      1 -
                      tankFill / 100
                    )
                } T896 ${
                  194 +
                  212 *
                    (
                      1 -
                      tankFill / 100
                    )
                }`}
              />

              <text
                x="835"
                y="220"
                textAnchor="middle"
              >
                BALLON
              </text>

              <text
                x="835"
                y="240"
                textAnchor="middle"
                className="gc-dt-svg-small"
              >
                TAMPON
              </text>
            </g>

            <g
              className={`gc-dt-pump ${
                scenario.pumpRunning &&
                scenario.safetySafe
                  ? "is-running"
                  : "is-stopped"
              }`}
            >
              <circle
                cx="985"
                cy="300"
                r="50"
              />

              <path
                className="gc-dt-pump-rotor"
                d="M985 263 C1017 263 1017 289 985 300 C953 311 953 337 985 337"
              />

              <circle
                cx="985"
                cy="300"
                r="8"
              />

              <text
                x="985"
                y="372"
                textAnchor="middle"
              >
                POMPE
              </text>
            </g>

            <g className="gc-dt-floor">
              <rect
                x="1035"
                y="195"
                width="205"
                height="210"
                rx="28"
              />

              <path
                className={
                  result.floorFlow
                    ? "is-active"
                    : ""
                }
                d="M1065 260 H1210 V285 H1065 V310 H1210 V335 H1065"
              />

              <text
                x="1137"
                y="230"
                textAnchor="middle"
              >
                PLANCHER
              </text>

              <text
                x="1137"
                y="385"
                textAnchor="middle"
                className="gc-dt-svg-small"
              >
                RAFRAÎCHISSANT
              </text>
            </g>

            <g className="gc-dt-room">
              <path
                d="M1245 245 L1320 185 L1390 245 V430 H1245 Z"
                fill="url(#dtRoomGradient)"
              />

              <path d="M1245 245 L1320 185 L1390 245" />

              <rect
                x="1270"
                y="285"
                width="45"
                height="70"
                rx="5"
              />

              <rect
                x="1330"
                y="280"
                width="38"
                height="38"
                rx="5"
              />

              <text
                x="1320"
                y="390"
                textAnchor="middle"
              >
                HABITATION
              </text>
            </g>

            <g transform="translate(175 235)">
              <rect
                className="gc-dt-temp-box"
                width="105"
                height="48"
                rx="10"
              />

              <text
                x="52.5"
                y="18"
                textAnchor="middle"
                className="gc-dt-temp-label"
              >
                SOURCE ENTRÉE
              </text>

              <text
                x="52.5"
                y="37"
                textAnchor="middle"
                className="gc-dt-temp-value"
              >
                {formatTemperature(
                  scenario.sourceInTemperature,
                )}
              </text>
            </g>

            <g transform="translate(438 318)">
              <rect
                className="gc-dt-temp-box"
                width="105"
                height="48"
                rx="10"
              />

              <text
                x="52.5"
                y="18"
                textAnchor="middle"
                className="gc-dt-temp-label"
              >
                SOURCE SORTIE
              </text>

              <text
                x="52.5"
                y="37"
                textAnchor="middle"
                className="gc-dt-temp-value"
              >
                {formatTemperature(
                  scenario.sourceOutTemperature,
                )}
              </text>
            </g>

            <g transform="translate(920 218)">
              <rect
                className="gc-dt-temp-box"
                width="105"
                height="48"
                rx="10"
              />

              <text
                x="52.5"
                y="18"
                textAnchor="middle"
                className="gc-dt-temp-label"
              >
                DÉPART
              </text>

              <text
                x="52.5"
                y="37"
                textAnchor="middle"
                className="gc-dt-temp-value"
              >
                {formatTemperature(
                  scenario.supplyTemperature,
                )}
              </text>
            </g>

            <g transform="translate(1010 445)">
              <rect
                className="gc-dt-temp-box"
                width="105"
                height="48"
                rx="10"
              />

              <text
                x="52.5"
                y="18"
                textAnchor="middle"
                className="gc-dt-temp-label"
              >
                RETOUR
              </text>

              <text
                x="52.5"
                y="37"
                textAnchor="middle"
                className="gc-dt-temp-value"
              >
                {formatTemperature(
                  scenario.returnTemperature,
                )}
              </text>
            </g>

            <g transform="translate(1265 105)">
              <rect
                className="gc-dt-room-box"
                width="120"
                height="58"
                rx="12"
              />

              <text
                x="60"
                y="20"
                textAnchor="middle"
                className="gc-dt-temp-label"
              >
                AMBIANCE
              </text>

              <text
                x="60"
                y="42"
                textAnchor="middle"
                className="gc-dt-room-value"
              >
                {formatTemperature(
                  scenario.indoorTemperature,
                )}
              </text>
            </g>

            {!scenario.safetySafe ? (
              <g className="gc-dt-safety-overlay">
                <rect
                  x="470"
                  y="55"
                  width="460"
                  height="72"
                  rx="18"
                />

                <text
                  x="700"
                  y="87"
                  textAnchor="middle"
                >
                  SÉCURITÉ ACTIVE — FLUX BLOQUÉS
                </text>

                <text
                  x="700"
                  y="108"
                  textAnchor="middle"
                  className="gc-dt-svg-small"
                >
                  Aucune commande physique depuis le jumeau
                </text>
              </g>
            ) : null}
          </svg>
        </div>

        <footer className="gc-dt-process__states">
          <article>
            <span>
              ÉLECTROVANNE
            </span>

            <strong
              className={
                scenario.valveOpen
                  ? "is-good"
                  : "is-neutral"
              }
            >
              {scenario.valveOpen
                ? "OUVERTE"
                : "FERMÉE"}
            </strong>
          </article>

          <article>
            <span>
              CIRCULATEUR
            </span>

            <strong
              className={
                scenario.pumpRunning
                  ? "is-good"
                  : "is-neutral"
              }
            >
              {scenario.pumpRunning
                ? "EN MARCHE"
                : "À L’ARRÊT"}
            </strong>
          </article>

          <article>
            <span>
              SÉCURITÉ
            </span>

            <strong
              className={
                scenario.safetySafe
                  ? "is-good"
                  : "is-critical"
              }
            >
              {scenario.safetySafe
                ? "VALIDÉE"
                : "BLOQUÉE"}
            </strong>
          </article>

          <article>
            <span>
              POINT DE ROSÉE
            </span>

            <strong>
              {formatTemperature(
                result.dewPoint,
              )}
            </strong>
          </article>

          <article>
            <span>
              PROJECTION AMBIANCE
            </span>

            <strong>
              {formatTemperature(
                result.projectedIndoorTemperature,
              )}
            </strong>
          </article>
        </footer>
      </section>

      <section className="gc-dt-projection">
        <header>
          <div>
            <p className="gc-page-header__eyebrow">
              PROJECTION THERMIQUE
            </p>

            <h3>
              Évolution estimée sur
              {" "}
              {projectionHours} heure(s)
            </h3>
          </div>

          <label>
            <span>
              HORIZON
            </span>

            <select
              value={projectionHours}
              onChange={(event) =>
                setProjectionHours(
                  Number(
                    event.target.value,
                  ),
                )
              }
            >
              <option value="1">
                1 heure
              </option>

              <option value="3">
                3 heures
              </option>

              <option value="6">
                6 heures
              </option>

              <option value="12">
                12 heures
              </option>

              <option value="24">
                24 heures
              </option>
            </select>
          </label>
        </header>

        <div className="gc-dt-projection__kpis">
          <article>
            <span>
              TEMPÉRATURE FINALE
            </span>

            <strong>
              {finalProjection
                ? formatTemperature(
                    finalProjection.indoorTemperature,
                  )
                : "—"}
            </strong>

            <small>
              Variation :
              {" "}
              {finalProjection
                ? `${
                    finalProjection.indoorTemperature -
                      scenario.indoorTemperature >
                    0
                      ? "+"
                      : ""
                  }${(
                    finalProjection.indoorTemperature -
                    scenario.indoorTemperature
                  ).toFixed(
                    1,
                  )} °C`
                : "—"}
            </small>
          </article>

          <article>
            <span>
              MARGE MINIMALE
            </span>

            <strong
              className={
                minimumCondensationMargin ===
                null
                  ? "is-neutral"
                  : minimumCondensationMargin >=
                      3
                    ? "is-good"
                    : minimumCondensationMargin >=
                        2
                      ? "is-warning"
                      : "is-critical"
              }
            >
              {minimumCondensationMargin ===
              null
                ? "—"
                : `${minimumCondensationMargin.toFixed(
                    1,
                  )} °C`}
            </strong>

            <small>
              Marge condensation projetée
            </small>
          </article>

          <article>
            <span>
              HEURES À RISQUE
            </span>

            <strong
              className={
                riskHours === 0
                  ? "is-good"
                  : "is-critical"
              }
            >
              {riskHours}
            </strong>

            <small>
              Marge inférieure à 3 °C
            </small>
          </article>

          <article>
            <span>
              CIRCULATION
            </span>

            <strong
              className={
                result.floorFlow
                  ? "is-good"
                  : "is-neutral"
              }
            >
              {result.floorFlow
                ? "ACTIVE"
                : "INACTIVE"}
            </strong>

            <small>
              Sur toute la projection
            </small>
          </article>
        </div>

        <div className="gc-dt-projection__chart">
          <div className="gc-dt-projection__axis">
            <span>
              {projectionTemperatureRange.maximum.toFixed(
                1,
              )} °C
            </span>

            <span>
              {(
                (
                  projectionTemperatureRange.maximum +
                  projectionTemperatureRange.minimum
                ) /
                2
              ).toFixed(
                1,
              )} °C
            </span>

            <span>
              {projectionTemperatureRange.minimum.toFixed(
                1,
              )} °C
            </span>
          </div>

          <div>
            <svg
              viewBox={`0 0 ${PROJECTION_WIDTH} ${PROJECTION_HEIGHT}`}
              preserveAspectRatio="none"
              role="img"
              aria-label="Projection de température du jumeau numérique"
            >
              <g className="gc-dt-projection-grid">
                <path d="M0 0 H1000" />
                <path d="M0 60 H1000" />
                <path d="M0 120 H1000" />
                <path d="M0 180 H1000" />
                <path d="M0 240 H1000" />

                <path d="M0 0 V240" />
                <path d="M250 0 V240" />
                <path d="M500 0 V240" />
                <path d="M750 0 V240" />
                <path d="M1000 0 V240" />
              </g>

              <path
                d={indoorProjectionPath}
                className="gc-dt-projection-line is-indoor"
              />

              <path
                d={dewPointProjectionPath}
                className="gc-dt-projection-line is-dewpoint"
              />
            </svg>

            <footer>
              <span>
                H+0
              </span>

              <span>
                H+
                {Math.round(
                  projectionHours / 2,
                )}
              </span>

              <span>
                H+{projectionHours}
              </span>
            </footer>
          </div>
        </div>

        <div className="gc-dt-projection__legend">
          <span className="is-indoor">
            <i />
            Température intérieure
          </span>

          <span className="is-dewpoint">
            <i />
            Point de rosée
          </span>
        </div>
      </section>

      <section className="gc-dt-comparison">
        <header>
          <div>
            <p className="gc-page-header__eyebrow">
              RÉEL / SIMULATION
            </p>

            <h3>
              Comparaison des conditions
            </h3>
          </div>

          <span>
            Les valeurs simulées ne sont jamais
            envoyées au contrôleur.
          </span>
        </header>

        <div>
          {comparisonMetrics.map(
            (metric) => (
              <article
                key={metric.label}
              >
                <span>
                  {metric.label}
                </span>

                <section>
                  <div>
                    <small>
                      RÉEL
                    </small>

                    <strong>
                      {metric.realtime ===
                      null
                        ? "—"
                        : `${metric.realtime.toFixed(
                            1,
                          )} ${metric.unit}`}
                    </strong>
                  </div>

                  <div>
                    <small>
                      SIMULATION
                    </small>

                    <strong>
                      {metric.simulation.toFixed(
                        1,
                      )}{" "}
                      {metric.unit}
                    </strong>
                  </div>
                </section>

                <footer
                  className={
                    metric.difference ===
                    null
                      ? "is-neutral"
                      : Math.abs(
                            metric.difference,
                          ) <
                          0.1
                        ? "is-neutral"
                        : "is-different"
                  }
                >
                  <span>
                    {metric.difference ===
                    null
                      ? "—"
                      : metric.difference >
                          0
                        ? "↗"
                        : metric.difference <
                            0
                          ? "↘"
                          : "→"}
                  </span>

                  <strong>
                    {metric.difference ===
                    null
                      ? "Non disponible"
                      : `${
                          metric.difference >
                          0
                            ? "+"
                            : ""
                        }${metric.difference.toFixed(
                          1,
                        )} ${
                          metric.unit
                        }`}
                  </strong>
                </footer>
              </article>
            ),
          )}
        </div>
      </section>

      <section className="gc-dt-layout">
        <article className="gc-dt-control-panel">
          <header>
            <div>
              <p className="gc-page-header__eyebrow">
                PARAMÈTRES DU MODÈLE
              </p>

              <h3>
                {mode === "simulation"
                  ? "Scénario modifiable"
                  : "Valeurs du contrôleur"}
              </h3>
            </div>

            <strong>
              {mode === "simulation"
                ? "LOCAL"
                : "LECTURE SEULE"}
            </strong>
          </header>

          <div className="gc-dt-controls">
            {[
              {
                key:
                  "indoorTemperature" as const,
                label:
                  "Température intérieure",
                min: 18,
                max: 32,
                step: 0.1,
                unit: "°C",
              },
              {
                key:
                  "humidity" as const,
                label:
                  "Humidité relative",
                min: 20,
                max: 90,
                step: 1,
                unit: "%",
              },
              {
                key:
                  "sourceInTemperature" as const,
                label:
                  "Source entrée",
                min: 5,
                max: 22,
                step: 0.1,
                unit: "°C",
              },
              {
                key:
                  "sourceOutTemperature" as const,
                label:
                  "Source sortie",
                min: 5,
                max: 28,
                step: 0.1,
                unit: "°C",
              },
              {
                key:
                  "supplyTemperature" as const,
                label:
                  "Départ plancher",
                min: 12,
                max: 26,
                step: 0.1,
                unit: "°C",
              },
              {
                key:
                  "returnTemperature" as const,
                label:
                  "Retour plancher",
                min: 12,
                max: 30,
                step: 0.1,
                unit: "°C",
              },
            ].map(
              (control) => (
                <label
                  key={control.key}
                >
                  <span>
                    {control.label}
                  </span>

                  <div>
                    <input
                      type="range"
                      min={control.min}
                      max={control.max}
                      step={control.step}
                      value={
                        scenario[
                          control.key
                        ]
                      }
                      disabled={
                        mode !==
                        "simulation"
                      }
                      onChange={(
                        event,
                      ) =>
                        updateNumber(
                          control.key,
                          event.target
                            .value,
                        )
                      }
                    />

                    <input
                      type="number"
                      min={control.min}
                      max={control.max}
                      step={control.step}
                      value={
                        scenario[
                          control.key
                        ]
                      }
                      disabled={
                        mode !==
                        "simulation"
                      }
                      onChange={(
                        event,
                      ) =>
                        updateNumber(
                          control.key,
                          event.target
                            .value,
                        )
                      }
                    />

                    <strong>
                      {control.unit}
                    </strong>
                  </div>
                </label>
              ),
            )}
          </div>

          <div className="gc-dt-switches">
            {[
              {
                key:
                  "valveOpen" as const,
                label:
                  "Électrovanne",
                active:
                  "Ouverte",
                inactive:
                  "Fermée",
              },
              {
                key:
                  "pumpRunning" as const,
                label:
                  "Circulateur",
                active:
                  "En marche",
                inactive:
                  "À l’arrêt",
              },
              {
                key:
                  "safetySafe" as const,
                label:
                  "Sécurité",
                active:
                  "Validée",
                inactive:
                  "Bloquée",
              },
            ].map(
              (control) => (
                <label
                  key={control.key}
                >
                  <input
                    type="checkbox"
                    checked={
                      scenario[
                        control.key
                      ]
                    }
                    disabled={
                      mode !==
                      "simulation"
                    }
                    onChange={(
                      event,
                    ) =>
                      updateBoolean(
                        control.key,
                        event.target
                          .checked,
                      )
                    }
                  />

                  <span />

                  <div>
                    <strong>
                      {control.label}
                    </strong>

                    <small>
                      {scenario[
                        control.key
                      ]
                        ? control.active
                        : control.inactive}
                    </small>
                  </div>
                </label>
              ),
            )}
          </div>
        </article>

        <article className="gc-dt-analysis-panel">
          <header>
            <div>
              <p className="gc-page-header__eyebrow">
                ANALYSE DU JUMEAU
              </p>

              <h3>
                Contrôles thermiques
              </h3>
            </div>

            <strong
              className={`is-${processTone}`}
            >
              {result.safe &&
              result.coherent
                ? "VALIDÉ"
                : "À SURVEILLER"}
            </strong>
          </header>

          <div>
            <article
              className={
                result.safe
                  ? "is-good"
                  : "is-critical"
              }
            >
              <span>
                {result.safe
                  ? "✓"
                  : "!"}
              </span>

              <div>
                <strong>
                  Sécurité condensation
                </strong>

                <small>
                  Marge actuelle :
                  {" "}
                  {result.condensationMargin.toFixed(
                    1,
                  )} °C
                </small>
              </div>
            </article>

            <article
              className={
                result.coherent
                  ? "is-good"
                  : "is-warning"
              }
            >
              <span>
                {result.coherent
                  ? "✓"
                  : "!"}
              </span>

              <div>
                <strong>
                  Cohérence hydraulique
                </strong>

                <small>
                  Pompe, vanne et ΔT contrôlés
                </small>
              </div>
            </article>

            <article
              className={
                result.sourceFlow
                  ? "is-good"
                  : "is-neutral"
              }
            >
              <span>
                {result.sourceFlow
                  ? "✓"
                  : "–"}
              </span>

              <div>
                <strong>
                  Circulation source
                </strong>

                <small>
                  {result.sourceFlow
                    ? "Échange source actif"
                    : "Source isolée"}
                </small>
              </div>
            </article>

            <article
              className={
                result.floorFlow
                  ? "is-good"
                  : "is-neutral"
              }
            >
              <span>
                {result.floorFlow
                  ? "✓"
                  : "–"}
              </span>

              <div>
                <strong>
                  Circulation plancher
                </strong>

                <small>
                  {result.floorFlow
                    ? "Rafraîchissement actif"
                    : "Plancher sans circulation"}
                </small>
              </div>
            </article>

            <article className="is-good">
              <span>✓</span>

              <div>
                <strong>
                  Isolation matérielle
                </strong>

                <small>
                  Aucun ordre envoyé au contrôleur
                </small>
              </div>
            </article>
          </div>

          <section className="gc-dt-analysis-values">
            <article>
              <span>
                ΔT SOURCE
              </span>

              <strong>
                {result.sourceDelta.toFixed(
                  1,
                )} °C
              </strong>
            </article>

            <article>
              <span>
                ΔT PLANCHER
              </span>

              <strong>
                {result.floorDelta.toFixed(
                  1,
                )} °C
              </strong>
            </article>

            <article>
              <span>
                POINT DE ROSÉE
              </span>

              <strong>
                {result.dewPoint.toFixed(
                  1,
                )} °C
              </strong>
            </article>

            <article>
              <span>
                REFROIDISSEMENT
              </span>

              <strong>
                −{result.thermalEffect.toFixed(
                  1,
                )} °C
              </strong>
            </article>
          </section>
        </article>
      </section>
    </AppShell>
  );
}
