"use client";

import Link from "next/link";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { AppShell } from "@/components/layout/AppShell";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useGeoCooling } from "@/hooks/useGeoCooling";
import type { GeoCoolingSnapshot } from "@/types/geocooling";

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
  deviceReady: boolean | null;
  confidence: number;
};

type TemperatureSeriesKey =
  | "indoorTemperature"
  | "sourceInTemperature"
  | "sourceOutTemperature"
  | "supplyTemperature"
  | "returnTemperature";

type PeriodKey =
  | "15m"
  | "1h"
  | "6h"
  | "24h"
  | "all";

type SeriesDefinition = {
  key: TemperatureSeriesKey;
  label: string;
  shortLabel: string;
  className: string;
};

type Statistics = {
  count: number;
  minimum: number | null;
  maximum: number | null;
  average: number | null;
  standardDeviation: number | null;
};

const STORAGE_KEY =
  "geocooling-ui-historian-enterprise-v2";

const LEGACY_STORAGE_KEY =
  "geocooling-ui-historian-v1";

const SAMPLE_INTERVAL_MS = 10_000;

/*
 * 8 640 points à 10 secondes représentent 24 heures.
 * Cette limite reste raisonnable pour localStorage.
 */
const MAX_POINTS = 8_640;

const CHART_WIDTH = 1_000;
const CHART_HEIGHT = 310;

const SERIES: SeriesDefinition[] = [
  {
    key: "indoorTemperature",
    label: "Température intérieure",
    shortLabel: "Intérieur",
    className: "is-indoor",
  },
  {
    key: "sourceInTemperature",
    label: "Source entrée",
    shortLabel: "Source E",
    className: "is-source-in",
  },
  {
    key: "sourceOutTemperature",
    label: "Source sortie",
    shortLabel: "Source S",
    className: "is-source-out",
  },
  {
    key: "supplyTemperature",
    label: "Départ plancher",
    shortLabel: "Départ",
    className: "is-supply",
  },
  {
    key: "returnTemperature",
    label: "Retour plancher",
    shortLabel: "Retour",
    className: "is-return",
  },
];

const PERIODS: Array<{
  key: PeriodKey;
  label: string;
  durationMs: number | null;
}> = [
  {
    key: "15m",
    label: "15 min",
    durationMs: 15 * 60 * 1_000,
  },
  {
    key: "1h",
    label: "1 h",
    durationMs: 60 * 60 * 1_000,
  },
  {
    key: "6h",
    label: "6 h",
    durationMs: 6 * 60 * 60 * 1_000,
  },
  {
    key: "24h",
    label: "24 h",
    durationMs: 24 * 60 * 60 * 1_000,
  },
  {
    key: "all",
    label: "Tout",
    durationMs: null,
  },
];

function isFiniteNumber(
  value: unknown,
): value is number {
  return (
    typeof value === "number" &&
    Number.isFinite(value)
  );
}

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

    deviceReady:
      snapshot.deviceReady,

    confidence:
      isFiniteNumber(
        snapshot.decision.confidence,
      )
        ? snapshot.decision.confidence
        : 0,
  };
}

function isHistoryPoint(
  value: unknown,
): value is HistoryPoint {
  if (
    typeof value !== "object" ||
    value === null
  ) {
    return false;
  }

  const point =
    value as Partial<HistoryPoint>;

  return (
    typeof point.timestamp === "string" &&
    typeof point.pumpRunning === "boolean" &&
    typeof point.valveOpen === "boolean"
  );
}

function normalizeStoredPoints(
  value: unknown,
): HistoryPoint[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value
    .filter(isHistoryPoint)
    .sort(
      (left, right) =>
        new Date(left.timestamp).getTime() -
        new Date(right.timestamp).getTime(),
    )
    .slice(-MAX_POINTS);
}

function readStoredHistory(): HistoryPoint[] {
  if (typeof window === "undefined") {
    return [];
  }

  try {
    const current =
      window.localStorage.getItem(
        STORAGE_KEY,
      );

    if (current) {
      return normalizeStoredPoints(
        JSON.parse(current),
      );
    }

    const legacy =
      window.localStorage.getItem(
        LEGACY_STORAGE_KEY,
      );

    if (!legacy) {
      return [];
    }

    const migrated =
      normalizeStoredPoints(
        JSON.parse(legacy),
      );

    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify(migrated),
    );

    return migrated;
  } catch {
    return [];
  }
}

function saveHistory(
  points: HistoryPoint[],
): void {
  try {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify(points),
    );
  } catch (error) {
    console.error(
      "[Historian] Impossible d’enregistrer les données",
      error,
    );
  }
}

function dateFromTimestamp(
  timestamp: string,
): Date | null {
  const value = new Date(timestamp);

  return Number.isNaN(value.getTime())
    ? null
    : value;
}

function formatTime(
  timestamp: string | null | undefined,
): string {
  if (!timestamp) {
    return "--:--:--";
  }

  const date =
    dateFromTimestamp(timestamp);

  if (!date) {
    return "--:--:--";
  }

  return date.toLocaleTimeString("fr-FR", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function formatDateTime(
  timestamp: string | null | undefined,
): string {
  if (!timestamp) {
    return "Non disponible";
  }

  const date =
    dateFromTimestamp(timestamp);

  if (!date) {
    return "Non disponible";
  }

  return date.toLocaleString("fr-FR", {
    dateStyle: "short",
    timeStyle: "medium",
  });
}

function formatDuration(
  milliseconds: number,
): string {
  const seconds =
    Math.max(
      0,
      Math.round(milliseconds / 1_000),
    );

  if (seconds < 60) {
    return `${seconds} s`;
  }

  const minutes =
    Math.floor(seconds / 60);

  if (minutes < 60) {
    return `${minutes} min`;
  }

  const hours =
    Math.floor(minutes / 60);

  const remainingMinutes =
    minutes % 60;

  return remainingMinutes === 0
    ? `${hours} h`
    : `${hours} h ${remainingMinutes} min`;
}

function formatNumber(
  value: number | null,
  digits = 1,
): string {
  return value === null
    ? "—"
    : value.toFixed(digits);
}

function statistics(
  values: Array<number | null>,
): Statistics {
  const valid =
    values.filter(isFiniteNumber);

  if (valid.length === 0) {
    return {
      count: 0,
      minimum: null,
      maximum: null,
      average: null,
      standardDeviation: null,
    };
  }

  const minimum =
    Math.min(...valid);

  const maximum =
    Math.max(...valid);

  const average =
    valid.reduce(
      (total, value) =>
        total + value,
      0,
    ) / valid.length;

  const variance =
    valid.reduce(
      (total, value) =>
        total +
        Math.pow(value - average, 2),
      0,
    ) / valid.length;

  return {
    count: valid.length,
    minimum,
    maximum,
    average,
    standardDeviation:
      Math.sqrt(variance),
  };
}

function mean(
  values: Array<number | null>,
): number | null {
  return statistics(values).average;
}

function periodDuration(
  period: PeriodKey,
): number | null {
  return (
    PERIODS.find(
      (candidate) =>
        candidate.key === period,
    )?.durationMs ?? null
  );
}

function filterByPeriod(
  points: HistoryPoint[],
  period: PeriodKey,
): HistoryPoint[] {
  const duration =
    periodDuration(period);

  if (
    duration === null ||
    points.length === 0
  ) {
    return points;
  }

  const latestTimestamp =
    new Date(
      points.at(-1)!.timestamp,
    ).getTime();

  const threshold =
    latestTimestamp - duration;

  return points.filter(
    (point) =>
      new Date(
        point.timestamp,
      ).getTime() >= threshold,
  );
}

function temperatureRange(
  points: HistoryPoint[],
  activeSeries: Set<TemperatureSeriesKey>,
): {
  minimum: number;
  maximum: number;
} {
  const values =
    points.flatMap((point) =>
      SERIES.filter(
        (series) =>
          activeSeries.has(series.key),
      ).map(
        (series) =>
          point[series.key],
      ),
    ).filter(isFiniteNumber);

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

  const spread =
    Math.max(
      1,
      rawMaximum - rawMinimum,
    );

  const margin =
    Math.max(
      0.8,
      spread * 0.12,
    );

  return {
    minimum:
      Math.floor(
        (rawMinimum - margin) * 2,
      ) / 2,

    maximum:
      Math.ceil(
        (rawMaximum + margin) * 2,
      ) / 2,
  };
}

function pathForSeries(
  points: HistoryPoint[],
  key: TemperatureSeriesKey,
  minimum: number,
  maximum: number,
): string {
  const span =
    Math.max(
      0.1,
      maximum - minimum,
    );

  const coordinates =
    points
      .map((point, index) => {
        const value = point[key];

        if (!isFiniteNumber(value)) {
          return null;
        }

        const x =
          points.length <= 1
            ? CHART_WIDTH / 2
            : (
                index /
                (points.length - 1)
              ) *
              CHART_WIDTH;

        const y =
          CHART_HEIGHT -
          (
            (value - minimum) /
            span
          ) *
          CHART_HEIGHT;

        return {
          x,
          y,
        };
      })
      .filter(
        (
          coordinate,
        ): coordinate is {
          x: number;
          y: number;
        } =>
          coordinate !== null,
      );

  return coordinates
    .map(
      (coordinate, index) =>
        `${
          index === 0 ? "M" : "L"
        } ${coordinate.x.toFixed(
          2,
        )} ${coordinate.y.toFixed(
          2,
        )}`,
    )
    .join(" ");
}

function valueToY(
  value: number,
  minimum: number,
  maximum: number,
): number {
  const span =
    Math.max(
      0.1,
      maximum - minimum,
    );

  return (
    CHART_HEIGHT -
    (
      (value - minimum) /
      span
    ) *
    CHART_HEIGHT
  );
}

function pointDelta(
  point: HistoryPoint,
  type: "source" | "floor",
): number | null {
  if (type === "source") {
    return (
      isFiniteNumber(
        point.sourceInTemperature,
      ) &&
      isFiniteNumber(
        point.sourceOutTemperature,
      )
    )
      ? point.sourceOutTemperature -
          point.sourceInTemperature
      : null;
  }

  return (
    isFiniteNumber(
      point.supplyTemperature,
    ) &&
    isFiniteNumber(
      point.returnTemperature,
    )
  )
    ? point.returnTemperature -
        point.supplyTemperature
    : null;
}

function downloadTextFile(
  content: string,
  filename: string,
  mimeType: string,
): void {
  const blob =
    new Blob([content], {
      type: mimeType,
    });

  const url =
    URL.createObjectURL(blob);

  const anchor =
    document.createElement("a");

  anchor.href = url;
  anchor.download = filename;
  anchor.click();

  URL.revokeObjectURL(url);
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

  const [paused, setPaused] =
    useState(false);

  const [period, setPeriod] =
    useState<PeriodKey>("1h");

  const [activeSeries, setActiveSeries] =
    useState<Set<TemperatureSeriesKey>>(
      () =>
        new Set(
          SERIES.map(
            (series) => series.key,
          ),
        ),
    );

  const [cursorIndex, setCursorIndex] =
    useState<number | null>(null);

  const lastStoredAtRef =
    useRef<number>(0);

  const connected =
    Boolean(snapshot && !error);

  useEffect(() => {
    const stored =
      readStoredHistory();

    setHistory(stored);

    const lastPoint =
      stored.at(-1);

    if (lastPoint) {
      lastStoredAtRef.current =
        new Date(
          lastPoint.timestamp,
        ).getTime();
    }

    setInitialized(true);
  }, []);

  useEffect(() => {
    if (
      !initialized ||
      !snapshot ||
      paused
    ) {
      return;
    }

    const point =
      createPoint(snapshot);

    const pointTimestamp =
      new Date(
        point.timestamp,
      ).getTime();

    if (
      !Number.isFinite(
        pointTimestamp,
      )
    ) {
      return;
    }

    if (
      pointTimestamp -
        lastStoredAtRef.current <
      SAMPLE_INTERVAL_MS
    ) {
      return;
    }

    lastStoredAtRef.current =
      pointTimestamp;

    setHistory((current) => {
      const previous =
        current.at(-1);

      if (
        previous?.timestamp ===
        point.timestamp
      ) {
        return current;
      }

      const updated =
        [...current, point]
          .sort(
            (left, right) =>
              new Date(
                left.timestamp,
              ).getTime() -
              new Date(
                right.timestamp,
              ).getTime(),
          )
          .slice(-MAX_POINTS);

      saveHistory(updated);

      return updated;
    });
  }, [
    initialized,
    paused,
    snapshot,
  ]);

  const visibleHistory =
    useMemo(
      () =>
        filterByPeriod(
          history,
          period,
        ),
      [history, period],
    );

  useEffect(() => {
    setCursorIndex(null);
  }, [
    period,
    visibleHistory.length,
  ]);

  const range =
    useMemo(
      () =>
        temperatureRange(
          visibleHistory,
          activeSeries,
        ),
      [
        visibleHistory,
        activeSeries,
      ],
    );

  const chartSeries =
    useMemo(
      () =>
        SERIES.filter(
          (series) =>
            activeSeries.has(
              series.key,
            ),
        ).map((series) => ({
          ...series,
          path: pathForSeries(
            visibleHistory,
            series.key,
            range.minimum,
            range.maximum,
          ),
        })),
      [
        visibleHistory,
        activeSeries,
        range,
      ],
    );

  const seriesStatistics =
    useMemo(
      () =>
        SERIES.map((series) => ({
          ...series,
          statistics: statistics(
            visibleHistory.map(
              (point) =>
                point[series.key],
            ),
          ),
        })),
      [visibleHistory],
    );

  const floorDeltaStatistics =
    useMemo(
      () =>
        statistics(
          visibleHistory.map(
            (point) =>
              pointDelta(
                point,
                "floor",
              ),
          ),
        ),
      [visibleHistory],
    );

  const sourceDeltaStatistics =
    useMemo(
      () =>
        statistics(
          visibleHistory.map(
            (point) =>
              pointDelta(
                point,
                "source",
              ),
          ),
        ),
      [visibleHistory],
    );

  const humidityStatistics =
    useMemo(
      () =>
        statistics(
          visibleHistory.map(
            (point) =>
              point.humidity,
          ),
        ),
      [visibleHistory],
    );

  const confidenceStatistics =
    useMemo(
      () =>
        statistics(
          visibleHistory.map(
            (point) =>
              point.confidence,
          ),
        ),
      [visibleHistory],
    );

  const activePoints =
    visibleHistory.filter(
      (point) =>
        point.pumpRunning &&
        point.valveOpen,
    ).length;

  const runtimeRatio =
    visibleHistory.length === 0
      ? 0
      : Math.round(
          (
            activePoints /
            visibleHistory.length
          ) *
            100,
        );

  const safetyEvents =
    visibleHistory.filter(
      (point) =>
        point.safetySafe === false,
    ).length;

  const estimatedStoredDuration =
    history.length <= 1
      ? 0
      : new Date(
          history.at(-1)!.timestamp,
        ).getTime() -
        new Date(
          history[0].timestamp,
        ).getTime();

  const storageUsage =
    typeof window === "undefined"
      ? 0
      : new Blob([
          JSON.stringify(history),
        ]).size;

  const storageUsageKilobytes =
    Math.round(storageUsage / 1_024);

  const selectedPoint =
    cursorIndex === null
      ? visibleHistory.at(-1) ?? null
      : visibleHistory[
          clamp(
            cursorIndex,
            0,
            Math.max(
              0,
              visibleHistory.length - 1,
            ),
          )
        ] ?? null;

  const selectedIndex =
    selectedPoint
      ? visibleHistory.indexOf(
          selectedPoint,
        )
      : -1;

  const selectedX =
    selectedIndex < 0 ||
    visibleHistory.length <= 1
      ? CHART_WIDTH
      : (
          selectedIndex /
          (visibleHistory.length - 1)
        ) *
        CHART_WIDTH;

  const handleChartMove =
    useCallback(
      (
        event: React.MouseEvent<
          SVGSVGElement
        >,
      ) => {
        if (
          visibleHistory.length === 0
        ) {
          return;
        }

        const bounds =
          event.currentTarget
            .getBoundingClientRect();

        const ratio =
          clamp(
            (
              event.clientX -
              bounds.left
            ) /
              bounds.width,
            0,
            1,
          );

        const index =
          Math.round(
            ratio *
              (
                visibleHistory.length -
                1
              ),
          );

        setCursorIndex(index);
      },
      [visibleHistory.length],
    );

  const toggleSeries =
    (
      key: TemperatureSeriesKey,
    ) => {
      setActiveSeries(
        (current) => {
          const next =
            new Set(current);

          if (next.has(key)) {
            if (next.size > 1) {
              next.delete(key);
            }
          } else {
            next.add(key);
          }

          return next;
        },
      );
    };

  const clearHistory = () => {
    setHistory([]);
    setCursorIndex(null);
    lastStoredAtRef.current = 0;

    try {
      window.localStorage.removeItem(
        STORAGE_KEY,
      );

      window.localStorage.removeItem(
        LEGACY_STORAGE_KEY,
      );
    } catch {
      // Le stockage local peut être indisponible.
    }
  };

  const exportCsv = () => {
    if (
      visibleHistory.length === 0
    ) {
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
      "source_delta_c",
      "floor_delta_c",
      "pump_running",
      "valve_open",
      "safety_safe",
      "device_ready",
      "brain_confidence",
    ];

    const rows =
      visibleHistory.map(
        (point) => [
          point.timestamp,
          point.indoorTemperature ?? "",
          point.humidity ?? "",
          point.sourceInTemperature ?? "",
          point.sourceOutTemperature ?? "",
          point.supplyTemperature ?? "",
          point.returnTemperature ?? "",
          pointDelta(
            point,
            "source",
          ) ?? "",
          pointDelta(
            point,
            "floor",
          ) ?? "",
          point.pumpRunning,
          point.valveOpen,
          point.safetySafe ?? "",
          point.deviceReady ?? "",
          point.confidence,
        ],
      );

    const csv =
      [
        header,
        ...rows,
      ]
        .map((row) =>
          row
            .map(
              (value) =>
                `"${String(
                  value,
                ).replaceAll(
                  '"',
                  '""',
                )}"`,
            )
            .join(";"),
        )
        .join("\n");

    downloadTextFile(
      csv,
      `geocooling-historian-${period}-${new Date()
        .toISOString()
        .replaceAll(":", "-")}.csv`,
      "text/csv;charset=utf-8",
    );
  };

  const exportJson = () => {
    if (
      visibleHistory.length === 0
    ) {
      return;
    }

    const payload = {
      exportedAt:
        new Date().toISOString(),

      period,

      sampleIntervalSeconds:
        SAMPLE_INTERVAL_MS / 1_000,

      pointCount:
        visibleHistory.length,

      statistics: {
        runtimeRatio,
        safetyEvents,
        humidity:
          humidityStatistics,
        confidence:
          confidenceStatistics,
        sourceDelta:
          sourceDeltaStatistics,
        floorDelta:
          floorDeltaStatistics,

        series:
          Object.fromEntries(
            seriesStatistics.map(
              (series) => [
                series.key,
                series.statistics,
              ],
            ),
          ),
      },

      points:
        visibleHistory,
    };

    downloadTextFile(
      JSON.stringify(
        payload,
        null,
        2,
      ),
      `geocooling-historian-${period}-${new Date()
        .toISOString()
        .replaceAll(":", "-")}.json`,
      "application/json;charset=utf-8",
    );
  };

  return (
    <AppShell
      connected={connected}
      mode={String(
        snapshot?.mode ?? "INCONNU",
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
            HISTORIAN ENTERPRISE
          </p>

          <h2>
            Séries temporelles GeoCooling
          </h2>

          <p>
            Acquisition locale échantillonnée,
            analyse statistique, curseur synchronisé,
            sélection de période et exports de données.
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
              paused
                ? "ACQUISITION PAUSE"
                : connected
                  ? "ACQUISITION ACTIVE"
                  : "SOURCE HORS LIGNE"
            }
            tone={
              paused
                ? "warning"
                : connected
                  ? "success"
                  : "danger"
            }
            pulse={
              connected && !paused
            }
          />
        </div>
      </section>

      <section className="gc-historian-enterprise-toolbar">
        <div className="gc-historian-enterprise-toolbar__status">
          <div
            className={
              connected && !paused
                ? "is-recording"
                : paused
                  ? "is-paused"
                  : "is-offline"
            }
          >
            <span />
          </div>

          <div>
            <strong>
              {paused
                ? "Acquisition suspendue"
                : connected
                  ? "Enregistrement local en cours"
                  : "En attente du contrôleur"}
            </strong>

            <small>
              Échantillonnage toutes les{" "}
              {SAMPLE_INTERVAL_MS / 1_000} secondes ·
              capacité maximale 24 heures
            </small>
          </div>
        </div>

        <div className="gc-historian-enterprise-toolbar__actions">
          <button
            type="button"
            onClick={() =>
              setPaused(
                (current) =>
                  !current,
              )
            }
          >
            {paused
              ? "Reprendre"
              : "Mettre en pause"}
          </button>

          <button
            type="button"
            onClick={exportCsv}
            disabled={
              visibleHistory.length === 0
            }
          >
            Export CSV
          </button>

          <button
            type="button"
            onClick={exportJson}
            disabled={
              visibleHistory.length === 0
            }
          >
            Export JSON
          </button>

          <button
            type="button"
            className="is-danger"
            onClick={clearHistory}
            disabled={
              history.length === 0
            }
          >
            Effacer
          </button>
        </div>
      </section>

      <section className="gc-historian-enterprise-kpis">
        <article>
          <span>POINTS EN MÉMOIRE</span>

          <strong>
            {history.length.toLocaleString(
              "fr-FR",
            )}
          </strong>

          <small>
            {visibleHistory.length.toLocaleString(
              "fr-FR",
            )}{" "}
            dans la période visible
          </small>
        </article>

        <article>
          <span>DURÉE ENREGISTRÉE</span>

          <strong>
            {formatDuration(
              estimatedStoredDuration,
            )}
          </strong>

          <small>
            Premier point{" "}
            {formatTime(
              history[0]?.timestamp,
            )}
          </small>
        </article>

        <article>
          <span>TAUX DE MARCHE</span>

          <strong>
            {runtimeRatio} %
          </strong>

          <small>
            Pompe et vanne actives
          </small>
        </article>

        <article>
          <span>ÉVÉNEMENTS SÉCURITÉ</span>

          <strong
            className={
              safetyEvents > 0
                ? "is-negative"
                : "is-positive"
            }
          >
            {safetyEvents}
          </strong>

          <small>
            Snapshots avec sécurité bloquante
          </small>
        </article>

        <article>
          <span>STOCKAGE LOCAL</span>

          <strong>
            {storageUsageKilobytes.toLocaleString(
              "fr-FR",
            )}{" "}
            Ko
          </strong>

          <small>
            Navigateur actuel uniquement
          </small>
        </article>
      </section>

      <section className="gc-historian-enterprise-chart">
        <header className="gc-historian-enterprise-chart__header">
          <div>
            <p className="gc-page-header__eyebrow">
              TENDANCES THERMIQUES
            </p>

            <h3>
              Courbes synchronisées
            </h3>
          </div>

          <div className="gc-historian-enterprise-periods">
            {PERIODS.map(
              (candidate) => (
                <button
                  key={candidate.key}
                  type="button"
                  className={
                    period ===
                    candidate.key
                      ? "is-active"
                      : ""
                  }
                  onClick={() =>
                    setPeriod(
                      candidate.key,
                    )
                  }
                >
                  {candidate.label}
                </button>
              ),
            )}
          </div>
        </header>

        <div className="gc-historian-enterprise-series">
          {SERIES.map((series) => {
            const active =
              activeSeries.has(
                series.key,
              );

            return (
              <button
                key={series.key}
                type="button"
                className={`${series.className} ${
                  active
                    ? "is-active"
                    : ""
                }`}
                onClick={() =>
                  toggleSeries(
                    series.key,
                  )
                }
                title={series.label}
              >
                <i />

                <span>
                  {series.shortLabel}
                </span>

                <strong>
                  {formatNumber(
                    selectedPoint?.[
                      series.key
                    ] ?? null,
                  )}
                  {" °C"}
                </strong>
              </button>
            );
          })}
        </div>

        {visibleHistory.length < 2 ? (
          <div className="gc-historian-enterprise-empty">
            <div aria-hidden="true">
              ⌁
            </div>

            <strong>
              Acquisition en cours
            </strong>

            <p>
              Deux points au minimum sont nécessaires
              pour afficher une courbe.
            </p>
          </div>
        ) : (
          <div className="gc-historian-enterprise-chart__body">
            <div className="gc-historian-enterprise-axis">
              <span>
                {range.maximum.toFixed(1)} °C
              </span>

              <span>
                {(
                  (
                    range.maximum +
                    range.minimum
                  ) /
                  2
                ).toFixed(1)}{" "}
                °C
              </span>

              <span>
                {range.minimum.toFixed(1)} °C
              </span>
            </div>

            <div className="gc-historian-enterprise-svg-wrap">
              <svg
                viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
                preserveAspectRatio="none"
                role="img"
                aria-label="Courbes temporelles GeoCooling"
                onMouseMove={
                  handleChartMove
                }
                onMouseLeave={() =>
                  setCursorIndex(null)
                }
              >
                <g className="gc-historian-enterprise-grid">
                  <path d="M0 0 H1000" />
                  <path d="M0 77.5 H1000" />
                  <path d="M0 155 H1000" />
                  <path d="M0 232.5 H1000" />
                  <path d="M0 310 H1000" />

                  <path d="M0 0 V310" />
                  <path d="M250 0 V310" />
                  <path d="M500 0 V310" />
                  <path d="M750 0 V310" />
                  <path d="M1000 0 V310" />
                </g>

                {chartSeries.map(
                  (series) =>
                    series.path ? (
                      <path
                        key={series.key}
                        d={series.path}
                        className={`gc-historian-enterprise-line ${series.className}`}
                      />
                    ) : null,
                )}

                {selectedPoint ? (
                  <g className="gc-historian-enterprise-cursor">
                    <line
                      x1={selectedX}
                      x2={selectedX}
                      y1="0"
                      y2={CHART_HEIGHT}
                    />

                    {chartSeries.map(
                      (series) => {
                        const value =
                          selectedPoint[
                            series.key
                          ];

                        if (
                          !isFiniteNumber(
                            value,
                          )
                        ) {
                          return null;
                        }

                        return (
                          <circle
                            key={series.key}
                            cx={selectedX}
                            cy={valueToY(
                              value,
                              range.minimum,
                              range.maximum,
                            )}
                            r="5"
                            className={
                              series.className
                            }
                          />
                        );
                      },
                    )}
                  </g>
                ) : null}

                <rect
                  x="0"
                  y="0"
                  width={CHART_WIDTH}
                  height={CHART_HEIGHT}
                  className="gc-historian-enterprise-hitbox"
                />
              </svg>

              <div className="gc-historian-enterprise-time-axis">
                <span>
                  {formatTime(
                    visibleHistory[0]
                      ?.timestamp,
                  )}
                </span>

                <span>
                  {formatTime(
                    visibleHistory[
                      Math.floor(
                        visibleHistory.length /
                          2,
                      )
                    ]?.timestamp,
                  )}
                </span>

                <span>
                  {formatTime(
                    visibleHistory.at(-1)
                      ?.timestamp,
                  )}
                </span>
              </div>
            </div>
          </div>
        )}

        <footer className="gc-historian-enterprise-cursor-panel">
          <div>
            <span>CURSEUR</span>

            <strong>
              {formatDateTime(
                selectedPoint?.timestamp,
              )}
            </strong>
          </div>

          <div>
            <span>HUMIDITÉ</span>

            <strong>
              {formatNumber(
                selectedPoint?.humidity ??
                  null,
              )}{" "}
              %
            </strong>
          </div>

          <div>
            <span>ΔT SOURCE</span>

            <strong>
              {formatNumber(
                selectedPoint
                  ? pointDelta(
                      selectedPoint,
                      "source",
                    )
                  : null,
              )}{" "}
              °C
            </strong>
          </div>

          <div>
            <span>ΔT PLANCHER</span>

            <strong>
              {formatNumber(
                selectedPoint
                  ? pointDelta(
                      selectedPoint,
                      "floor",
                    )
                  : null,
              )}{" "}
              °C
            </strong>
          </div>

          <div>
            <span>CONFIANCE BRAIN</span>

            <strong>
              {formatNumber(
                selectedPoint?.confidence ??
                  null,
                0,
              )}{" "}
              %
            </strong>
          </div>

          <div>
            <span>CIRCUIT</span>

            <strong
              className={
                selectedPoint?.pumpRunning &&
                selectedPoint?.valveOpen
                  ? "is-positive"
                  : "is-neutral"
              }
            >
              {selectedPoint?.pumpRunning &&
              selectedPoint?.valveOpen
                ? "ACTIF"
                : "ARRÊT"}
            </strong>
          </div>
        </footer>
      </section>

      <section className="gc-historian-enterprise-analysis">
        <article className="gc-historian-enterprise-statistics">
          <header>
            <div>
              <p className="gc-page-header__eyebrow">
                ANALYSE STATISTIQUE
              </p>

              <h3>
                Températures de la période
              </h3>
            </div>

            <strong>
              {visibleHistory.length.toLocaleString(
                "fr-FR",
              )}{" "}
              points
            </strong>
          </header>

          <div className="gc-historian-enterprise-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Série</th>
                  <th>Min.</th>
                  <th>Max.</th>
                  <th>Moy.</th>
                  <th>Écart type</th>
                  <th>Mesures</th>
                </tr>
              </thead>

              <tbody>
                {seriesStatistics.map(
                  (series) => (
                    <tr key={series.key}>
                      <td>
                        <span
                          className={`gc-historian-enterprise-table-series ${series.className}`}
                        >
                          <i />
                          {series.shortLabel}
                        </span>
                      </td>

                      <td>
                        {formatNumber(
                          series.statistics
                            .minimum,
                        )}{" "}
                        °C
                      </td>

                      <td>
                        {formatNumber(
                          series.statistics
                            .maximum,
                        )}{" "}
                        °C
                      </td>

                      <td>
                        {formatNumber(
                          series.statistics
                            .average,
                        )}{" "}
                        °C
                      </td>

                      <td>
                        {formatNumber(
                          series.statistics
                            .standardDeviation,
                          2,
                        )}{" "}
                        °C
                      </td>

                      <td>
                        {series.statistics.count.toLocaleString(
                          "fr-FR",
                        )}
                      </td>
                    </tr>
                  ),
                )}
              </tbody>
            </table>
          </div>
        </article>

        <aside className="gc-historian-enterprise-summary">
          <header>
            <p className="gc-page-header__eyebrow">
              INDICATEURS CALCULÉS
            </p>

            <h3>
              Synthèse de la période
            </h3>
          </header>

          <div>
            <article>
              <span>ΔT SOURCE MOYEN</span>

              <strong>
                {formatNumber(
                  sourceDeltaStatistics.average,
                )}{" "}
                °C
              </strong>

              <small>
                Min.{" "}
                {formatNumber(
                  sourceDeltaStatistics.minimum,
                )}{" "}
                · Max.{" "}
                {formatNumber(
                  sourceDeltaStatistics.maximum,
                )}
              </small>
            </article>

            <article>
              <span>ΔT PLANCHER MOYEN</span>

              <strong>
                {formatNumber(
                  floorDeltaStatistics.average,
                )}{" "}
                °C
              </strong>

              <small>
                Min.{" "}
                {formatNumber(
                  floorDeltaStatistics.minimum,
                )}{" "}
                · Max.{" "}
                {formatNumber(
                  floorDeltaStatistics.maximum,
                )}
              </small>
            </article>

            <article>
              <span>HUMIDITÉ MOYENNE</span>

              <strong>
                {formatNumber(
                  humidityStatistics.average,
                )}{" "}
                %
              </strong>

              <small>
                Étendue{" "}
                {formatNumber(
                  humidityStatistics.minimum,
                )}{" "}
                à{" "}
                {formatNumber(
                  humidityStatistics.maximum,
                )}{" "}
                %
              </small>
            </article>

            <article>
              <span>CONFIANCE MOYENNE</span>

              <strong>
                {formatNumber(
                  confidenceStatistics.average,
                  0,
                )}{" "}
                %
              </strong>

              <small>
                Écart type{" "}
                {formatNumber(
                  confidenceStatistics
                    .standardDeviation,
                  1,
                )}
              </small>
            </article>

            <article>
              <span>INTÉRIEUR MOYEN</span>

              <strong>
                {formatNumber(
                  mean(
                    visibleHistory.map(
                      (point) =>
                        point.indoorTemperature,
                    ),
                  ),
                )}{" "}
                °C
              </strong>

              <small>
                Période sélectionnée :{" "}
                {
                  PERIODS.find(
                    (candidate) =>
                      candidate.key ===
                      period,
                  )?.label
                }
              </small>
            </article>
          </div>
        </aside>
      </section>

      <section className="gc-historian-enterprise-events">
        <header>
          <div>
            <p className="gc-page-header__eyebrow">
              JOURNAL RÉCENT
            </p>

            <h3>
              Derniers échantillons
            </h3>
          </div>

          <span>
            25 dernières entrées visibles
          </span>
        </header>

        <div className="gc-historian-enterprise-table-wrap">
          <table>
            <thead>
              <tr>
                <th>Horodatage</th>
                <th>Intérieur</th>
                <th>Humidité</th>
                <th>Source E/S</th>
                <th>Plancher D/R</th>
                <th>ΔT sol</th>
                <th>Pompe</th>
                <th>Vanne</th>
                <th>Sécurité</th>
              </tr>
            </thead>

            <tbody>
              {[...visibleHistory]
                .slice(-25)
                .reverse()
                .map((point) => (
                  <tr key={point.timestamp}>
                    <td>
                      {formatDateTime(
                        point.timestamp,
                      )}
                    </td>

                    <td>
                      {formatNumber(
                        point.indoorTemperature,
                      )}{" "}
                      °C
                    </td>

                    <td>
                      {formatNumber(
                        point.humidity,
                      )}{" "}
                      %
                    </td>

                    <td>
                      {formatNumber(
                        point.sourceInTemperature,
                      )}
                      {" / "}
                      {formatNumber(
                        point.sourceOutTemperature,
                      )}{" "}
                      °C
                    </td>

                    <td>
                      {formatNumber(
                        point.supplyTemperature,
                      )}
                      {" / "}
                      {formatNumber(
                        point.returnTemperature,
                      )}{" "}
                      °C
                    </td>

                    <td>
                      {formatNumber(
                        pointDelta(
                          point,
                          "floor",
                        ),
                      )}{" "}
                      °C
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
