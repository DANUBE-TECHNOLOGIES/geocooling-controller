"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import type { GeoCoolingSnapshot } from "@/types/geocooling";
import { AppShell } from "@/components/layout/AppShell";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useGeoCooling } from "@/hooks/useGeoCooling";

type TwinScenario = {
  indoorTemperature: number;
  humidity: number;
  sourceTemperature: number;
  supplyTemperature: number;
  returnTemperature: number;
  circuitActive: boolean;
};

type TwinResult = {
  dewPoint: number;
  condensationMargin: number;
  sourceDelta: number;
  floorDelta: number;
  projectedIndoorTemperature: number;
  thermalEffect: number;
  safe: boolean;
  coherent: boolean;
};

function validNumber(
  value: number | null | undefined,
): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function numberOr(
  value: number | null | undefined,
  fallback: number,
): number {
  return validNumber(value) ? value : fallback;
}

function calculateDewPoint(
  temperature: number,
  humidity: number,
): number {
  const boundedHumidity = Math.min(
    100,
    Math.max(1, humidity),
  );

  const a = 17.62;
  const b = 243.12;

  const gamma =
    Math.log(boundedHumidity / 100) +
    (a * temperature) / (b + temperature);

  return (b * gamma) / (a - gamma);
}

function calculateTwin(
  scenario: TwinScenario,
): TwinResult {
  const dewPoint = calculateDewPoint(
    scenario.indoorTemperature,
    scenario.humidity,
  );

  const condensationMargin =
    scenario.supplyTemperature - dewPoint;

  const sourceDelta =
    scenario.supplyTemperature -
    scenario.sourceTemperature;

  const floorDelta =
    scenario.returnTemperature -
    scenario.supplyTemperature;

  const hydraulicEffect =
    scenario.circuitActive
      ? Math.max(
          0,
          Math.min(
            2.5,
            Math.abs(floorDelta) * 0.45 +
              Math.max(0, sourceDelta) * 0.08,
          ),
        )
      : 0;

  const projectedIndoorTemperature =
    scenario.indoorTemperature -
    hydraulicEffect;

  return {
    dewPoint,
    condensationMargin,
    sourceDelta,
    floorDelta,
    projectedIndoorTemperature,
    thermalEffect: hydraulicEffect,
    safe: condensationMargin >= 3,
    coherent:
      floorDelta >= -0.5 &&
      floorDelta <= 6,
  };
}

function buildInitialScenario(
  snapshot: GeoCoolingSnapshot | null,
): TwinScenario {
  return {
    indoorTemperature: numberOr(
      snapshot?.indoorTemperature,
      25,
    ),

    humidity: numberOr(
      snapshot?.humidity,
      55,
    ),

    sourceTemperature: numberOr(
      snapshot?.sourceInTemperature,
      13,
    ),

    supplyTemperature: numberOr(
      snapshot?.supplyTemperature,
      18,
    ),

    returnTemperature: numberOr(
      snapshot?.returnTemperature,
      20,
    ),

    circuitActive: Boolean(
      snapshot?.pumpRunning &&
      snapshot?.valveOpen,
    ),
  };
}

function format(
  value: number,
): string {
  return value.toFixed(1);
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

  const connected = Boolean(snapshot && !error);

  const [scenario, setScenario] =
    useState<TwinScenario>(() =>
      buildInitialScenario(null),
    );

  const [initialized, setInitialized] =
    useState(false);

  if (snapshot && !initialized) {
    setScenario(buildInitialScenario(snapshot));
    setInitialized(true);
  }

  const result = useMemo(
    () => calculateTwin(scenario),
    [scenario],
  );

  const resetScenario = () => {
    setScenario(buildInitialScenario(snapshot));
  };

  const updateNumber = (
    key: keyof Omit<
      TwinScenario,
      "circuitActive"
    >,
    value: string,
  ) => {
    const parsed = Number(value);

    if (!Number.isFinite(parsed)) {
      return;
    }

    setScenario((current) => ({
      ...current,
      [key]: parsed,
    }));
  };

  const safetyTone =
    result.safe && result.coherent
      ? "success"
      : result.condensationMargin < 2
        ? "danger"
        : "warning";

  return (
    <AppShell
      connected={connected}
      mode={String(
        snapshot?.mode ?? "INCONNU",
      )}
      refreshing={refreshing}
      lastUpdate={lastUpdate}
      generatedAt={snapshot?.generatedAt}
      responseTime={responseTime}
      onRefresh={() => {
        void refresh();
      }}
    >
      <section className="gc-page-header">
        <div>
          <p className="gc-page-header__eyebrow">
            MODÈLE THERMIQUE INTERACTIF
          </p>

          <h2>Jumeau numérique</h2>

          <p>
            Simulation locale et sans commande
            matérielle permettant de tester un
            scénario thermique à partir du snapshot
            courant.
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
              result.safe &&
              result.coherent
                ? "SCÉNARIO SÛR"
                : "À SURVEILLER"
            }
            tone={safetyTone}
          />
        </div>
      </section>

      <section className="gc-twin-warning">
        <strong>
          Simulation locale uniquement
        </strong>

        <p>
          Les réglages de cette page ne sont jamais
          envoyés au backend, au Waveshare ou aux
          relais. Le modèle reste volontairement
          simplifié tant que l’apprentissage thermique
          persistant n’est pas exposé par l’API.
        </p>
      </section>

      {loading && !snapshot ? (
        <section className="gc-loading-state">
          <div className="gc-loading-spinner" />

          <div>
            <strong>
              Chargement du modèle…
            </strong>

            <span>
              Lecture du premier snapshot.
            </span>
          </div>
        </section>
      ) : null}

      <section className="gc-twin-layout">
        <article className="gc-twin-controls">
          <header>
            <div>
              <span className="gc-twin-label">
                PARAMÈTRES DU SCÉNARIO
              </span>

              <h3>
                Conditions simulées
              </h3>
            </div>

            <button
              type="button"
              onClick={resetScenario}
            >
              Reprendre le réel
            </button>
          </header>

          <div className="gc-twin-inputs">
            <label>
              <span>
                Température intérieure
              </span>

              <div>
                <input
                  type="range"
                  min="18"
                  max="32"
                  step="0.1"
                  value={
                    scenario.indoorTemperature
                  }
                  onChange={(event) =>
                    updateNumber(
                      "indoorTemperature",
                      event.target.value,
                    )
                  }
                />

                <input
                  type="number"
                  min="18"
                  max="32"
                  step="0.1"
                  value={
                    scenario.indoorTemperature
                  }
                  onChange={(event) =>
                    updateNumber(
                      "indoorTemperature",
                      event.target.value,
                    )
                  }
                />

                <strong>°C</strong>
              </div>
            </label>

            <label>
              <span>Humidité relative</span>

              <div>
                <input
                  type="range"
                  min="20"
                  max="90"
                  step="1"
                  value={scenario.humidity}
                  onChange={(event) =>
                    updateNumber(
                      "humidity",
                      event.target.value,
                    )
                  }
                />

                <input
                  type="number"
                  min="20"
                  max="90"
                  step="1"
                  value={scenario.humidity}
                  onChange={(event) =>
                    updateNumber(
                      "humidity",
                      event.target.value,
                    )
                  }
                />

                <strong>%</strong>
              </div>
            </label>

            <label>
              <span>
                Température source
              </span>

              <div>
                <input
                  type="range"
                  min="5"
                  max="22"
                  step="0.1"
                  value={
                    scenario.sourceTemperature
                  }
                  onChange={(event) =>
                    updateNumber(
                      "sourceTemperature",
                      event.target.value,
                    )
                  }
                />

                <input
                  type="number"
                  min="5"
                  max="22"
                  step="0.1"
                  value={
                    scenario.sourceTemperature
                  }
                  onChange={(event) =>
                    updateNumber(
                      "sourceTemperature",
                      event.target.value,
                    )
                  }
                />

                <strong>°C</strong>
              </div>
            </label>

            <label>
              <span>
                Départ plancher
              </span>

              <div>
                <input
                  type="range"
                  min="12"
                  max="26"
                  step="0.1"
                  value={
                    scenario.supplyTemperature
                  }
                  onChange={(event) =>
                    updateNumber(
                      "supplyTemperature",
                      event.target.value,
                    )
                  }
                />

                <input
                  type="number"
                  min="12"
                  max="26"
                  step="0.1"
                  value={
                    scenario.supplyTemperature
                  }
                  onChange={(event) =>
                    updateNumber(
                      "supplyTemperature",
                      event.target.value,
                    )
                  }
                />

                <strong>°C</strong>
              </div>
            </label>

            <label>
              <span>
                Retour plancher
              </span>

              <div>
                <input
                  type="range"
                  min="12"
                  max="30"
                  step="0.1"
                  value={
                    scenario.returnTemperature
                  }
                  onChange={(event) =>
                    updateNumber(
                      "returnTemperature",
                      event.target.value,
                    )
                  }
                />

                <input
                  type="number"
                  min="12"
                  max="30"
                  step="0.1"
                  value={
                    scenario.returnTemperature
                  }
                  onChange={(event) =>
                    updateNumber(
                      "returnTemperature",
                      event.target.value,
                    )
                  }
                />

                <strong>°C</strong>
              </div>
            </label>
          </div>

          <label className="gc-twin-switch">
            <input
              type="checkbox"
              checked={scenario.circuitActive}
              onChange={(event) =>
                setScenario((current) => ({
                  ...current,
                  circuitActive:
                    event.target.checked,
                }))
              }
            />

            <span />

            <div>
              <strong>
                Circuit hydraulique simulé
              </strong>

              <small>
                {scenario.circuitActive
                  ? "Pompe et vanne considérées actives"
                  : "Circuit considéré à l’arrêt"}
              </small>
            </div>
          </label>
        </article>

        <article className="gc-twin-visual">
          <header>
            <div>
              <span className="gc-twin-label">
                REPRÉSENTATION DU MODÈLE
              </span>

              <h3>
                Équilibre thermique
              </h3>
            </div>

            <strong>
              {scenario.circuitActive
                ? "ACTIF"
                : "VEILLE"}
            </strong>
          </header>

          <div className="gc-twin-process">
            <article>
              <span>SOURCE</span>
              <strong>
                {format(
                  scenario.sourceTemperature,
                )} °C
              </strong>
              <small>
                Ressource géothermique
              </small>
            </article>

            <div
              className={
                scenario.circuitActive
                  ? "gc-twin-flow is-active"
                  : "gc-twin-flow"
              }
            >
              <i />
              <i />
              <i />
            </div>

            <article>
              <span>DÉPART</span>
              <strong>
                {format(
                  scenario.supplyTemperature,
                )} °C
              </strong>
              <small>
                Vers plancher
              </small>
            </article>

            <div
              className={
                scenario.circuitActive
                  ? "gc-twin-flow is-active"
                  : "gc-twin-flow"
              }
            >
              <i />
              <i />
              <i />
            </div>

            <article>
              <span>RETOUR</span>
              <strong>
                {format(
                  scenario.returnTemperature,
                )} °C
              </strong>
              <small>
                Après échange bâtiment
              </small>
            </article>
          </div>

          <div className="gc-twin-room">
            <div
              className="gc-twin-room__temperature"
              style={{
                height: `${Math.min(
                  100,
                  Math.max(
                    10,
                    ((scenario.indoorTemperature -
                      18) /
                      14) *
                      100,
                  ),
                )}%`,
              }}
            />

            <div className="gc-twin-room__content">
              <span>
                AMBIANCE SIMULÉE
              </span>

              <strong>
                {format(
                  scenario.indoorTemperature,
                )} °C
              </strong>

              <small>
                Projection après cycle :
                {" "}
                {format(
                  result.projectedIndoorTemperature,
                )} °C
              </small>
            </div>
          </div>
        </article>
      </section>

      <section className="gc-twin-results">
        <article
          className={
            result.safe
              ? "is-good"
              : result.condensationMargin < 2
                ? "is-critical"
                : "is-warning"
          }
        >
          <span>MARGE CONDENSATION</span>

          <strong>
            {format(
              result.condensationMargin,
            )} °C
          </strong>

          <small>
            Départ moins point de rosée
          </small>
        </article>

        <article>
          <span>POINT DE ROSÉE</span>

          <strong>
            {format(result.dewPoint)} °C
          </strong>

          <small>
            Calcul température / humidité
          </small>
        </article>

        <article
          className={
            result.coherent
              ? "is-good"
              : "is-warning"
          }
        >
          <span>DELTA PLANCHER</span>

          <strong>
            {format(result.floorDelta)} °C
          </strong>

          <small>
            Retour moins départ
          </small>
        </article>

        <article>
          <span>EFFET ESTIMÉ</span>

          <strong>
            −{format(
              result.thermalEffect,
            )} °C
          </strong>

          <small>
            Impact simplifié par cycle
          </small>
        </article>

        <article>
          <span>ÉCART SOURCE / DÉPART</span>

          <strong>
            {format(result.sourceDelta)} °C
          </strong>

          <small>
            Potentiel thermique brut
          </small>
        </article>
      </section>

      <section className="gc-twin-validation">
        <header>
          <div>
            <span className="gc-twin-label">
              VALIDATION DU SCÉNARIO
            </span>

            <h3>
              Contrôles du jumeau
            </h3>
          </div>
        </header>

        <div>
          <article
            className={
              result.safe
                ? "is-valid"
                : "is-critical"
            }
          >
            <span>
              {result.safe ? "✓" : "!"}
            </span>

            <div>
              <strong>
                Sécurité condensation
              </strong>

              <small>
                {result.safe
                  ? "Marge supérieure ou égale à 3 °C"
                  : "Température de départ trop proche du point de rosée"}
              </small>
            </div>
          </article>

          <article
            className={
              result.coherent
                ? "is-valid"
                : "is-warning"
            }
          >
            <span>
              {result.coherent ? "✓" : "!"}
            </span>

            <div>
              <strong>
                Cohérence hydraulique
              </strong>

              <small>
                {result.coherent
                  ? "Delta plancher plausible"
                  : "Delta plancher hors plage simplifiée"}
              </small>
            </div>
          </article>

          <article
            className={
              scenario.circuitActive
                ? "is-valid"
                : "is-neutral"
            }
          >
            <span>
              {scenario.circuitActive
                ? "✓"
                : "–"}
            </span>

            <div>
              <strong>
                Activation du circuit
              </strong>

              <small>
                {scenario.circuitActive
                  ? "Effet thermique calculé"
                  : "Aucun rafraîchissement simulé"}
              </small>
            </div>
          </article>

          <article className="is-valid">
            <span>✓</span>

            <div>
              <strong>
                Isolation matérielle
              </strong>

              <small>
                Aucune commande n’est publiée
              </small>
            </div>
          </article>
        </div>
      </section>
    </AppShell>
  );
}
