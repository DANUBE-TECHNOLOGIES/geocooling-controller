"use client";

import Link from "next/link";
import {
  useEffect,
  useMemo,
  useState,
} from "react";
import type { GeoCoolingSnapshot } from "@/types/geocooling";
import { AppShell } from "@/components/layout/AppShell";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useGeoCooling } from "@/hooks/useGeoCooling";

type HistoryPoint = {
  timestamp: string;
  indoorTemperature: number | null;
  humidity: number | null;
  sourceInTemperature: number | null;
  sourceOutTemperature: number | null;
  supplyTemperature: number | null;
  returnTemperature: number | null;
  pumpRunning: boolean;
  valveOpen: boolean;
  safetySafe: boolean | null;
  confidence: number;
};

type SeriesDefinition = {
  key:
    | "indoorTemperature"
    | "sourceInTemperature"
    | "sourceOutTemperature"
    | "supplyTemperature"
    | "returnTemperature";
  label: string;
  className: string;
};

const STORAGE_KEY =
  "geocooling-ui-historian-v1";

const MAX_POINTS = 720;

const SERIES: SeriesDefinition[] = [
  {
    key: "indoorTemperature",
    label: "Intérieure",
    className: "is-indoor",
  },
  {
    key: "sourceInTemperature",
    label: "Source entrée",
    className: "is-source-in",
  },
  {
    key: "sourceOutTemperature",
    label: "Source sortie",
    className: "is-source-out",
  },
  {
    key: "supplyTemperature",
    label: "Départ plancher",
    className: "is-supply",
  },
  {
    key: "returnTemperature",
    label: "Retour plancher",
    className: "is-return",
  },
];

function validNumber(
  value: unknown,
): value is number {
  return (
    typeof value === "number" &&
    Number.isFinite(value)
  );
}

function createPoint(
  snapshot: GeoCoolingSnapshot,
): HistoryPoint {
  return {
    timestamp:
      snapshot.generatedAt ||
      new Date().toISOString(),

    indoorTemperature:
      snapshot.indoorTemperature,

    humidity:
      snapshot.humidity,

    sourceInTemperature:
      snapshot.sourceInTemperature,

    sourceOutTemperature:
      snapshot.sourceOutTemperature,

    supplyTemperature:
      snapshot.supplyTemperature,

    returnTemperature:
      snapshot.returnTemperature,

    pumpRunning:
      snapshot.pumpRunning,

    valveOpen:
      snapshot.valveOpen,

    safetySafe:
      snapshot.safetySafe,

    confidence:
      validNumber(snapshot.decision.confidence)
        ? snapshot.decision.confidence
        : 0,
  };
}

function readStoredHistory(): HistoryPoint[] {
  if (typeof window === "undefined") {
    return [];
  }

  try {
    const raw =
      window.localStorage.getItem(STORAGE_KEY);

    if (!raw) {
      return [];
    }

    const parsed = JSON.parse(raw);

    return Array.isArray(parsed)
      ? parsed.slice(-MAX_POINTS)
      : [];
  } catch {
    return [];
  }
}

function formatTime(
  timestamp: string,
): string {
  const date = new Date(timestamp);

  if (Number.isNaN(date.getTime())) {
    return "--:--";
  }

  return date.toLocaleTimeString("fr-FR", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function formatDateTime(
  timestamp: string | null,
): string {
  if (!timestamp) {
    return "Non disponible";
  }

  const date = new Date(timestamp);

  if (Number.isNaN(date.getTime())) {
    return "Non disponible";
  }

  return date.toLocaleString("fr-FR", {
    dateStyle: "short",
    timeStyle: "medium",
  });
}

function rangeForSeries(
  history: HistoryPoint[],
): {
  min: number;
  max: number;
} {
  const values = history.flatMap((point) =>
    SERIES.map((series) => point[series.key]),
  ).filter(validNumber);

  if (values.length === 0) {
    return {
      min: 0,
      max: 30,
    };
  }

  const minimum = Math.min(...values);
  const maximum = Math.max(...values);

  const margin = Math.max(
    1,
    (maximum - minimum) * 0.15,
  );

  return {
    min: Math.floor(minimum - margin),
    max: Math.ceil(maximum + margin),
  };
}

function pathForSeries(
  history: HistoryPoint[],
  key: SeriesDefinition["key"],
  min: number,
  max: number,
): string {
  const width = 1000;
  const height = 280;
  const span = Math.max(1, max - min);

  const points = history
    .map((point, index) => {
      const value = point[key];

      if (!validNumber(value)) {
        return null;
      }

      const x =
        history.length <= 1
          ? 0
          : (index / (history.length - 1)) *
            width;

      const y =
        height -
        ((value - min) / span) * height;

      return {
        x,
        y,
      };
    })
    .filter(
      (
        point,
      ): point is {
        x: number;
        y: number;
      } => point !== null,
    );

  if (points.length === 0) {
    return "";
  }

  return points
    .map(
      (point, index) =>
        `${index === 0 ? "M" : "L"} ${point.x.toFixed(
          1,
        )} ${point.y.toFixed(1)}`,
    )
    .join(" ");
}

function average(
  values: Array<number | null>,
): number | null {
  const valid = values.filter(validNumber);

  if (valid.length === 0) {
    return null;
  }

  return (
    valid.reduce(
      (total, value) => total + value,
      0,
    ) / valid.length
  );
}

function formatNumber(
  value: number | null,
  digits = 1,
): string {
  return value === null
    ? "—"
    : value.toFixed(digits);
}

export default function HistorianPage() {
  const {
    snapshot,
    loading,
    refreshing,
    error,
    lastUpdate,
    responseTime,
    refresh,
  } = useGeoCooling();

  const [history, setHistory] =
    useState<HistoryPoint[]>([]);

  const [initialized, setInitialized] =
    useState(false);

  const connected = Boolean(snapshot && !error);

  useEffect(() => {
    setHistory(readStoredHistory());
    setInitialized(true);
  }, []);

  useEffect(() => {
    if (!initialized || !snapshot) {
      return;
    }

    const point = createPoint(snapshot);

    setHistory((current) => {
      const last = current.at(-1);

      if (
        last?.timestamp === point.timestamp
      ) {
        return current;
      }

      const updated = [
        ...current,
        point,
      ].slice(-MAX_POINTS);

      try {
        window.localStorage.setItem(
          STORAGE_KEY,
          JSON.stringify(updated),
        );
      } catch {
        // Le stockage local peut être indisponible.
      }

      return updated;
    });
  }, [initialized, snapshot]);

  const range = useMemo(
    () => rangeForSeries(history),
    [history],
  );

  const chartPaths = useMemo(
    () =>
      SERIES.map((series) => ({
        ...series,
        path: pathForSeries(
          history,
          series.key,
          range.min,
          range.max,
        ),
      })),
    [history, range],
  );

  const averages = useMemo(
    () => ({
      indoor: average(
        history.map(
          (point) =>
            point.indoorTemperature,
        ),
      ),

      supply: average(
        history.map(
          (point) =>
            point.supplyTemperature,
        ),
      ),

      returnTemperature: average(
        history.map(
          (point) =>
            point.returnTemperature,
        ),
      ),

      humidity: average(
        history.map(
          (point) => point.humidity,
        ),
      ),

      confidence: average(
        history.map(
          (point) => point.confidence,
        ),
      ),
    }),
    [history],
  );

  const activePoints = history.filter(
    (point) =>
      point.pumpRunning &&
      point.valveOpen,
  ).length;

  const runtimeRatio =
    history.length === 0
      ? 0
      : Math.round(
          (activePoints / history.length) *
            100,
        );

  const clearHistory = () => {
    setHistory([]);

    try {
      window.localStorage.removeItem(
        STORAGE_KEY,
      );
    } catch {
      // Ignoré.
    }
  };

  const exportCsv = () => {
    if (history.length === 0) {
      return;
    }

    const header = [
      "timestamp",
      "indoor_temperature_c",
      "humidity_percent",
      "source_in_c",
      "source_out_c",
      "supply_c",
      "return_c",
      "pump_running",
      "valve_open",
      "safety_safe",
      "brain_confidence",
    ];

    const rows = history.map((point) => [
      point.timestamp,
      point.indoorTemperature ?? "",
      point.humidity ?? "",
      point.sourceInTemperature ?? "",
      point.sourceOutTemperature ?? "",
      point.supplyTemperature ?? "",
      point.returnTemperature ?? "",
      point.pumpRunning,
      point.valveOpen,
      point.safetySafe ?? "",
      point.confidence,
    ]);

    const csv = [
      header,
      ...rows,
    ]
      .map((row) =>
        row
          .map((value) =>
            `"${String(value).replaceAll(
              '"',
              '""',
            )}"`,
          )
          .join(";"),
      )
      .join("\n");

    const blob = new Blob([csv], {
      type: "text/csv;charset=utf-8",
    });

    const url =
      URL.createObjectURL(blob);

    const anchor =
      document.createElement("a");

    anchor.href = url;
    anchor.download =
      `geocooling-history-${new Date()
        .toISOString()
        .replaceAll(":", "-")}.csv`;

    anchor.click();

    URL.revokeObjectURL(url);
  };

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
            ACQUISITION LOCALE
          </p>

          <h2>Historian temps réel</h2>

          <p>
            Conservation locale des snapshots
            reçus par l’interface, visualisation
            des tendances thermiques et export CSV.
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
              history.length > 0
                ? `${history.length} POINTS`
                : "AUCUNE DONNÉE"
            }
            tone={
              history.length > 0
                ? "success"
                : "neutral"
            }
          />
        </div>
      </section>

      <section className="gc-historian-toolbar">
        <div>
          <strong>
            Historisation navigateur active
          </strong>

          <span>
            Jusqu’à {MAX_POINTS} snapshots,
            soit environ une heure à cinq
            secondes d’intervalle.
          </span>
        </div>

        <div>
          <button
            type="button"
            onClick={exportCsv}
            disabled={history.length === 0}
          >
            Exporter CSV
          </button>

          <button
            type="button"
            className="is-danger"
            onClick={clearHistory}
            disabled={history.length === 0}
          >
            Effacer l’historique
          </button>
        </div>
      </section>

      <section className="gc-historian-kpis">
        <article>
          <span>POINTS STOCKÉS</span>
          <strong>{history.length}</strong>
          <small>
            Maximum {MAX_POINTS}
          </small>
        </article>

        <article>
          <span>PREMIER POINT</span>
          <strong>
            {history.length > 0
              ? formatTime(
                  history[0].timestamp,
                )
              : "—"}
          </strong>
          <small>
            {formatDateTime(
              history[0]?.timestamp ?? null,
            )}
          </small>
        </article>

        <article>
          <span>DERNIER POINT</span>
          <strong>
            {history.length > 0
              ? formatTime(
                  history.at(-1)!.timestamp,
                )
              : "—"}
          </strong>
          <small>
            {formatDateTime(
              history.at(-1)?.timestamp ??
                null,
            )}
          </small>
        </article>

        <article>
          <span>TAUX DE MARCHE</span>
          <strong>{runtimeRatio} %</strong>
          <small>
            Pompe et vanne actives
          </small>
        </article>
      </section>

      <section className="gc-historian-chart">
        <header>
          <div>
            <span className="gc-page-header__eyebrow">
              TENDANCES THERMIQUES
            </span>

            <h3>
              Températures enregistrées
            </h3>
          </div>

          <div className="gc-historian-legend">
            {SERIES.map((series) => (
              <span
                key={series.key}
                className={series.className}
              >
                <i />
                {series.label}
              </span>
            ))}
          </div>
        </header>

        {history.length < 2 ? (
          <div className="gc-historian-empty">
            <strong>
              Acquisition en cours
            </strong>

            <p>
              Deux snapshots au minimum sont
              nécessaires pour afficher une
              tendance.
            </p>
          </div>
        ) : (
          <div className="gc-historian-chart__canvas">
            <div className="gc-historian-axis">
              <span>
                {range.max.toFixed(0)} °C
              </span>

              <span>
                {(
                  (range.max + range.min) /
                  2
                ).toFixed(0)} °C
              </span>

              <span>
                {range.min.toFixed(0)} °C
              </span>
            </div>

            <svg
              viewBox="0 0 1000 280"
              preserveAspectRatio="none"
              role="img"
              aria-label="Historique des températures GeoCooling"
            >
              <g className="gc-historian-grid">
                <path d="M0 0 H1000" />
                <path d="M0 70 H1000" />
                <path d="M0 140 H1000" />
                <path d="M0 210 H1000" />
                <path d="M0 280 H1000" />

                <path d="M0 0 V280" />
                <path d="M250 0 V280" />
                <path d="M500 0 V280" />
                <path d="M750 0 V280" />
                <path d="M1000 0 V280" />
              </g>

              {chartPaths.map((series) =>
                series.path ? (
                  <path
                    key={series.key}
                    d={series.path}
                    className={`gc-historian-series ${series.className}`}
                  />
                ) : null,
              )}
            </svg>

            <div className="gc-historian-time-axis">
              <span>
                {formatTime(
                  history[0].timestamp,
                )}
              </span>

              <span>
                {formatTime(
                  history[
                    Math.floor(
                      history.length / 2,
                    )
                  ].timestamp,
                )}
              </span>

              <span>
                {formatTime(
                  history.at(-1)!.timestamp,
                )}
              </span>
            </div>
          </div>
        )}
      </section>

      <section className="gc-historian-summary">
        <article>
          <span>
            TEMPÉRATURE INTÉRIEURE MOYENNE
          </span>

          <strong>
            {formatNumber(
              averages.indoor,
            )} °C
          </strong>
        </article>

        <article>
          <span>
            HUMIDITÉ MOYENNE
          </span>

          <strong>
            {formatNumber(
              averages.humidity,
            )} %
          </strong>
        </article>

        <article>
          <span>
            DÉPART MOYEN
          </span>

          <strong>
            {formatNumber(
              averages.supply,
            )} °C
          </strong>
        </article>

        <article>
          <span>
            RETOUR MOYEN
          </span>

          <strong>
            {formatNumber(
              averages.returnTemperature,
            )} °C
          </strong>
        </article>

        <article>
          <span>
            CONFIANCE BRAIN MOYENNE
          </span>

          <strong>
            {formatNumber(
              averages.confidence,
              0,
            )} %
          </strong>
        </article>
      </section>

      <section className="gc-historian-table">
        <header>
          <div>
            <span className="gc-page-header__eyebrow">
              DERNIERS SNAPSHOTS
            </span>

            <h3>
              Journal d’acquisition
            </h3>
          </div>

          <span>
            20 dernières entrées
          </span>
        </header>

        <div className="gc-historian-table__scroll">
          <table>
            <thead>
              <tr>
                <th>Heure</th>
                <th>Intérieur</th>
                <th>Humidité</th>
                <th>Source E/S</th>
                <th>Plancher D/R</th>
                <th>Pompe</th>
                <th>Vanne</th>
                <th>Sécurité</th>
              </tr>
            </thead>

            <tbody>
              {[...history]
                .slice(-20)
                .reverse()
                .map((point) => (
                  <tr key={point.timestamp}>
                    <td>
                      {formatTime(
                        point.timestamp,
                      )}
                    </td>

                    <td>
                      {formatNumber(
                        point.indoorTemperature,
                      )} °C
                    </td>

                    <td>
                      {formatNumber(
                        point.humidity,
                      )} %
                    </td>

                    <td>
                      {formatNumber(
                        point.sourceInTemperature,
                      )}
                      {" / "}
                      {formatNumber(
                        point.sourceOutTemperature,
                      )} °C
                    </td>

                    <td>
                      {formatNumber(
                        point.supplyTemperature,
                      )}
                      {" / "}
                      {formatNumber(
                        point.returnTemperature,
                      )} °C
                    </td>

                    <td>
                      <span
                        className={
                          point.pumpRunning
                            ? "gc-table-status is-positive"
                            : "gc-table-status is-neutral"
                        }
                      >
                        {point.pumpRunning
                          ? "ON"
                          : "OFF"}
                      </span>
                    </td>

                    <td>
                      <span
                        className={
                          point.valveOpen
                            ? "gc-table-status is-positive"
                            : "gc-table-status is-neutral"
                        }
                      >
                        {point.valveOpen
                          ? "OUVERTE"
                          : "FERMÉE"}
                      </span>
                    </td>

                    <td>
                      <span
                        className={
                          point.safetySafe === false
                            ? "gc-table-status is-negative"
                            : "gc-table-status is-positive"
                        }
                      >
                        {point.safetySafe === false
                          ? "ALARME"
                          : "OK"}
                      </span>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </section>
    </AppShell>
  );
}
