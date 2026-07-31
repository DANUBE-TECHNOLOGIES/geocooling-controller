"use client";

import { useMemo, useState } from "react";

import type { GeoCoolingSnapshot } from "@/types/geocooling";

type SimulationPanelProps = {
  snapshot: GeoCoolingSnapshot;
};

type SimulationValues = {
  indoorTemperature: number;
  humidity: number;
  sourceTemperature: number;
  supplyTemperature: number;
};

function finiteValue(
  value: number | null,
  fallback: number,
): number {
  return typeof value === "number" && Number.isFinite(value)
    ? value
    : fallback;
}

function calculateDewPoint(
  temperature: number,
  humidity: number,
): number {
  const a = 17.62;
  const b = 243.12;

  const safeHumidity = Math.min(
    Math.max(humidity, 1),
    100,
  );

  const gamma =
    Math.log(safeHumidity / 100) +
    (a * temperature) / (b + temperature);

  return (b * gamma) / (a - gamma);
}

function formatTemperature(value: number): string {
  return `${value.toFixed(1)} °C`;
}

export default function SimulationPanel({
  snapshot,
}: SimulationPanelProps) {
  const initialValues = useMemo<SimulationValues>(
    () => ({
      indoorTemperature: finiteValue(
        snapshot.indoorTemperature,
        25,
      ),
      humidity: finiteValue(
        snapshot.humidity,
        55,
      ),
      sourceTemperature: finiteValue(
        snapshot.sourceInTemperature,
        12,
      ),
      supplyTemperature: finiteValue(
        snapshot.supplyTemperature,
        18,
      ),
    }),
    [
      snapshot.humidity,
      snapshot.indoorTemperature,
      snapshot.sourceInTemperature,
      snapshot.supplyTemperature,
    ],
  );

  const [enabled, setEnabled] = useState(false);
  const [values, setValues] =
    useState<SimulationValues>(initialValues);

  const dewPoint = calculateDewPoint(
    values.indoorTemperature,
    values.humidity,
  );

  const condensationMargin =
    values.supplyTemperature - dewPoint;

  const condensationSafe =
    condensationMargin >= 3;

  const coolingDemand =
    values.indoorTemperature >= 25;

  const sourceAvailable =
    values.sourceTemperature <=
    values.indoorTemperature - 3;

  const simulatedActivation =
    enabled &&
    coolingDemand &&
    sourceAvailable &&
    condensationSafe;

  function updateValue(
    key: keyof SimulationValues,
    value: number,
  ) {
    setValues((current) => ({
      ...current,
      [key]: value,
    }));
  }

  function resetSimulation() {
    setValues(initialValues);
  }

  return (
    <article className="panel simulation-panel">
      <div className="panel-head">
        <div>
          <h2 className="panel-title">
            Mode simulation
          </h2>

          <div className="panel-kicker">
            Digital Twin local — aucune commande matérielle
          </div>
        </div>

        <button
          type="button"
          className={
            enabled
              ? "simulation-toggle simulation-toggle-active"
              : "simulation-toggle"
          }
          onClick={() => setEnabled((current) => !current)}
          aria-pressed={enabled}
        >
          <span className="simulation-toggle-dot" />

          {enabled ? "SIMULATION ACTIVE" : "ACTIVER"}
        </button>
      </div>

      <div className="simulation-warning">
        <strong>Environnement isolé.</strong>

        Les valeurs ci-dessous restent dans le navigateur et
        ne pilotent ni la pompe, ni la vanne, ni le contrôleur.
      </div>

      <div
        className={
          enabled
            ? "simulation-controls"
            : "simulation-controls simulation-controls-disabled"
        }
      >
        <label className="simulation-control">
          <span className="simulation-control-head">
            <span>Température intérieure</span>

            <strong>
              {formatTemperature(
                values.indoorTemperature,
              )}
            </strong>
          </span>

          <input
            type="range"
            min="18"
            max="35"
            step="0.1"
            value={values.indoorTemperature}
            disabled={!enabled}
            onChange={(event) =>
              updateValue(
                "indoorTemperature",
                Number(event.target.value),
              )
            }
          />
        </label>

        <label className="simulation-control">
          <span className="simulation-control-head">
            <span>Humidité intérieure</span>

            <strong>
              {values.humidity.toFixed(0)} %
            </strong>
          </span>

          <input
            type="range"
            min="25"
            max="95"
            step="1"
            value={values.humidity}
            disabled={!enabled}
            onChange={(event) =>
              updateValue(
                "humidity",
                Number(event.target.value),
              )
            }
          />
        </label>

        <label className="simulation-control">
          <span className="simulation-control-head">
            <span>Température de nappe</span>

            <strong>
              {formatTemperature(
                values.sourceTemperature,
              )}
            </strong>
          </span>

          <input
            type="range"
            min="5"
            max="24"
            step="0.1"
            value={values.sourceTemperature}
            disabled={!enabled}
            onChange={(event) =>
              updateValue(
                "sourceTemperature",
                Number(event.target.value),
              )
            }
          />
        </label>

        <label className="simulation-control">
          <span className="simulation-control-head">
            <span>Départ plancher simulé</span>

            <strong>
              {formatTemperature(
                values.supplyTemperature,
              )}
            </strong>
          </span>

          <input
            type="range"
            min="14"
            max="24"
            step="0.1"
            value={values.supplyTemperature}
            disabled={!enabled}
            onChange={(event) =>
              updateValue(
                "supplyTemperature",
                Number(event.target.value),
              )
            }
          />
        </label>
      </div>

      <div className="simulation-results">
        <div className="simulation-result">
          <span>Point de rosée</span>

          <strong>
            {formatTemperature(dewPoint)}
          </strong>
        </div>

        <div
          className={
            condensationSafe
              ? "simulation-result simulation-result-ok"
              : "simulation-result simulation-result-danger"
          }
        >
          <span>Marge condensation</span>

          <strong>
            {condensationMargin.toFixed(1)} °C
          </strong>
        </div>

        <div
          className={
            sourceAvailable
              ? "simulation-result simulation-result-ok"
              : "simulation-result simulation-result-warning"
          }
        >
          <span>Potentiel source</span>

          <strong>
            {sourceAvailable
              ? "SUFFISANT"
              : "INSUFFISANT"}
          </strong>
        </div>

        <div
          className={
            simulatedActivation
              ? "simulation-result simulation-result-running"
              : "simulation-result"
          }
        >
          <span>Décision simulée</span>

          <strong>
            {!enabled
              ? "INACTIVE"
              : simulatedActivation
                ? "DÉMARRAGE"
                : "ARRÊT"}
          </strong>
        </div>
      </div>

      <div className="simulation-actions">
        <button
          type="button"
          className="simulation-reset"
          onClick={resetSimulation}
          disabled={!enabled}
        >
          Réinitialiser les valeurs
        </button>
      </div>
    </article>
  );
}
