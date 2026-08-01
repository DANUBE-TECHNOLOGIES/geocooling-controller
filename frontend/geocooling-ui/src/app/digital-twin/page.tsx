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
  };

  const loadRealtimeIntoSimulation =
    () => {
      setSimulation(
        buildScenario(snapshot),
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
