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

type ImportMode =
  | "merge"
  | "replace";

type ImportStatus = {
  tone:
    | "success"
    | "warning"
    | "danger";
  message: string;
};

type ComparisonMetric = {
  label: string;
  unit: string;
  current: number | null;
  previous: number | null;
  difference: number | null;
  inversePositive?: boolean;
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

function parseNullableNumber(
  value: unknown,
): number | null {
  if (
    value === null ||
    value === undefined ||
    value === ""
  ) {
    return null;
  }

  if (
    typeof value === "number" &&
    Number.isFinite(value)
  ) {
    return value;
  }

  if (typeof value !== "string") {
    return null;
  }

  const normalized =
    value
      .trim()
      .replace(",", ".");

  if (!normalized) {
    return null;
  }

  const parsed =
    Number(normalized);

  return Number.isFinite(parsed)
    ? parsed
    : null;
}

function parseNullableBoolean(
  value: unknown,
): boolean | null {
  if (
    value === null ||
    value === undefined ||
    value === ""
  ) {
    return null;
  }

  if (typeof value === "boolean") {
    return value;
  }

  if (typeof value === "number") {
    return value !== 0;
  }

  const normalized =
    String(value)
      .trim()
      .toLowerCase();

  if (
    [
      "true",
      "1",
      "on",
      "yes",
      "oui",
      "active",
      "actif",
      "ouverte",
      "open",
      "ok",
    ].includes(normalized)
  ) {
    return true;
  }

  if (
    [
      "false",
      "0",
      "off",
      "no",
      "non",
      "inactive",
      "inactif",
      "fermee",
      "fermée",
      "closed",
      "alarme",
    ].includes(normalized)
  ) {
    return false;
  }

  return null;
}

function normalizeImportedPoint(
  value: unknown,
): HistoryPoint | null {
  if (
    typeof value !== "object" ||
    value === null
  ) {
    return null;
  }

  const source =
    value as Record<string, unknown>;

  const timestampValue =
    source.timestamp ??
    source.generatedAt ??
    source.generated_at ??
    source.date;

  if (
    typeof timestampValue !== "string"
  ) {
    return null;
  }

  const timestamp =
    new Date(timestampValue);

  if (
    Number.isNaN(
      timestamp.getTime(),
    )
  ) {
    return null;
  }

  return {
    timestamp:
      timestamp.toISOString(),

    indoorTemperature:
      parseNullableNumber(
        source.indoorTemperature ??
        source.indoor_temperature_c ??
        source.indoor_temperature,
      ),

    humidity:
      parseNullableNumber(
        source.humidity ??
        source.humidity_percent,
      ),

    sourceInTemperature:
      parseNullableNumber(
        source.sourceInTemperature ??
        source.source_in_c ??
        source.source_in_temperature,
      ),

    sourceOutTemperature:
      parseNullableNumber(
        source.sourceOutTemperature ??
        source.source_out_c ??
        source.source_out_temperature,
      ),

    supplyTemperature:
      parseNullableNumber(
        source.supplyTemperature ??
        source.supply_c ??
        source.supply_temperature,
      ),

    returnTemperature:
      parseNullableNumber(
        source.returnTemperature ??
        source.return_c ??
        source.return_temperature,
      ),

    pumpRunning:
      parseNullableBoolean(
        source.pumpRunning ??
        source.pump_running,
      ) ?? false,

    valveOpen:
      parseNullableBoolean(
        source.valveOpen ??
        source.valve_open,
      ) ?? false,

    safetySafe:
      parseNullableBoolean(
        source.safetySafe ??
        source.safety_safe,
      ),

    deviceReady:
      parseNullableBoolean(
        source.deviceReady ??
        source.device_ready,
      ),

    confidence:
      parseNullableNumber(
        source.confidence ??
        source.brain_confidence,
      ) ?? 0,
  };
}

function splitCsvLine(
  line: string,
  separator: string,
): string[] {
  const cells: string[] = [];
  let current = "";
  let quoted = false;

  for (
    let index = 0;
    index < line.length;
    index += 1
  ) {
    const character =
      line[index];

    if (character === '"') {
      const next =
        line[index + 1];

      if (
        quoted &&
        next === '"'
      ) {
        current += '"';
        index += 1;
      } else {
        quoted = !quoted;
      }

      continue;
    }

    if (
      character === separator &&
      !quoted
    ) {
      cells.push(
        current.trim(),
      );

      current = "";
      continue;
    }

    current += character;
  }

  cells.push(
    current.trim(),
  );

  return cells;
}

function parseCsvHistory(
  content: string,
): HistoryPoint[] {
  const lines =
    content
      .replace(/^\uFEFF/, "")
      .split(/\r?\n/)
      .filter(
        (line) =>
          line.trim().length > 0,
      );

  if (lines.length < 2) {
    return [];
  }

  const separator =
    lines[0].includes(";")
      ? ";"
      : ",";

  const headers =
    splitCsvLine(
      lines[0],
      separator,
    ).map(
      (header) =>
        header
          .trim()
          .replace(/^"|"$/g, ""),
    );

  return lines
    .slice(1)
    .map((line) => {
      const cells =
        splitCsvLine(
          line,
          separator,
        );

      const record:
        Record<string, unknown> = {};

      headers.forEach(
        (header, index) => {
          record[header] =
            cells[index] ?? "";
        },
      );

      return normalizeImportedPoint(
        record,
      );
    })
    .filter(
      (
        point,
      ): point is HistoryPoint =>
        point !== null,
    );
}

function parseJsonHistory(
  content: string,
): HistoryPoint[] {
  const parsed =
    JSON.parse(content);

  const candidates =
    Array.isArray(parsed)
      ? parsed
      : (
          typeof parsed === "object" &&
          parsed !== null &&
          Array.isArray(
            (
              parsed as {
                points?: unknown;
              }
            ).points,
          )
        )
        ? (
            parsed as {
              points: unknown[];
            }
          ).points
        : [];

  return candidates
    .map(
      normalizeImportedPoint,
    )
    .filter(
      (
        point,
      ): point is HistoryPoint =>
        point !== null,
    );
}

function mergeHistoryPoints(
  current: HistoryPoint[],
  imported: HistoryPoint[],
): HistoryPoint[] {
  const pointsByTimestamp =
    new Map<
      string,
      HistoryPoint
    >();

  current.forEach((point) => {
    pointsByTimestamp.set(
      point.timestamp,
      point,
    );
  });

  imported.forEach((point) => {
    pointsByTimestamp.set(
      point.timestamp,
      point,
    );
  });

  return Array.from(
    pointsByTimestamp.values(),
  )
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
}

function difference(
  current: number | null,
  previous: number | null,
): number | null {
  if (
    current === null ||
    previous === null
  ) {
    return null;
  }

  return current - previous;
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

  const [windowSizeRatio, setWindowSizeRatio] =
    useState(1);

  const [windowEndRatio, setWindowEndRatio] =
    useState(1);

  const [importMode, setImportMode] =
    useState<ImportMode>("merge");

  const [importing, setImporting] =
    useState(false);

  const [importStatus, setImportStatus] =
    useState<ImportStatus | null>(
      null,
    );

  const importInputRef =
    useRef<HTMLInputElement | null>(
      null,
    );

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

  const periodHistory =
    useMemo(
      () =>
        filterByPeriod(
          history,
          period,
        ),
      [history, period],
    );

  const visibleHistory =
    useMemo(() => {
      if (periodHistory.length <= 2) {
        return periodHistory;
      }

      const boundedSizeRatio =
        clamp(
          windowSizeRatio,
          0.1,
          1,
        );

      const boundedEndRatio =
        clamp(
          windowEndRatio,
          boundedSizeRatio,
          1,
        );

      const visibleCount =
        Math.max(
          2,
          Math.round(
            periodHistory.length *
              boundedSizeRatio,
          ),
        );

      const endIndex =
        Math.max(
          visibleCount,
          Math.round(
            periodHistory.length *
              boundedEndRatio,
          ),
        );

      const startIndex =
        Math.max(
          0,
          endIndex - visibleCount,
        );

      return periodHistory.slice(
        startIndex,
        Math.min(
          periodHistory.length,
          endIndex,
        ),
      );
    }, [
      periodHistory,
      windowSizeRatio,
      windowEndRatio,
    ]);

  useEffect(() => {
    setCursorIndex(null);
  }, [
    period,
    visibleHistory.length,
  ]);

  useEffect(() => {
    setWindowSizeRatio(1);
    setWindowEndRatio(1);
  }, [period]);

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

  const previousHistory =
    useMemo(() => {
      if (
        visibleHistory.length === 0 ||
        periodHistory.length === 0
      ) {
        return [];
      }

      const visibleStart =
        new Date(
          visibleHistory[0].timestamp,
        ).getTime();

      const visibleEnd =
        new Date(
          visibleHistory.at(-1)!.timestamp,
        ).getTime();

      const duration =
        Math.max(
          SAMPLE_INTERVAL_MS,
          visibleEnd - visibleStart,
        );

      const previousStart =
        visibleStart - duration;

      return periodHistory.filter(
        (point) => {
          const timestamp =
            new Date(
              point.timestamp,
            ).getTime();

          return (
            timestamp >= previousStart &&
            timestamp < visibleStart
          );
        },
      );
    }, [
      visibleHistory,
      periodHistory,
    ]);

  const previousFloorDeltaStatistics =
    useMemo(
      () =>
        statistics(
          previousHistory.map(
            (point) =>
              pointDelta(
                point,
                "floor",
              ),
          ),
        ),
      [previousHistory],
    );

  const previousSourceDeltaStatistics =
    useMemo(
      () =>
        statistics(
          previousHistory.map(
            (point) =>
              pointDelta(
                point,
                "source",
              ),
          ),
        ),
      [previousHistory],
    );

  const previousIndoorStatistics =
    useMemo(
      () =>
        statistics(
          previousHistory.map(
            (point) =>
              point.indoorTemperature,
          ),
        ),
      [previousHistory],
    );

  const previousHumidityStatistics =
    useMemo(
      () =>
        statistics(
          previousHistory.map(
            (point) =>
              point.humidity,
          ),
        ),
      [previousHistory],
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

  const previousActivePoints =
    previousHistory.filter(
      (point) =>
        point.pumpRunning &&
        point.valveOpen,
    ).length;

  const previousRuntimeRatio =
    previousHistory.length === 0
      ? null
      : Math.round(
          (
            previousActivePoints /
            previousHistory.length
          ) *
            100,
        );

  const currentIndoorStatistics =
    statistics(
      visibleHistory.map(
        (point) =>
          point.indoorTemperature,
      ),
    );

  const comparisonMetrics:
    ComparisonMetric[] = [
      {
        label:
          "Température intérieure",
        unit: "°C",
        current:
          currentIndoorStatistics.average,
        previous:
          previousIndoorStatistics.average,
        difference: difference(
          currentIndoorStatistics.average,
          previousIndoorStatistics.average,
        ),
        inversePositive: true,
      },
      {
        label: "Humidité",
        unit: "%",
        current:
          humidityStatistics.average,
        previous:
          previousHumidityStatistics.average,
        difference: difference(
          humidityStatistics.average,
          previousHumidityStatistics.average,
        ),
        inversePositive: true,
      },
      {
        label: "ΔT source",
        unit: "°C",
        current:
          sourceDeltaStatistics.average,
        previous:
          previousSourceDeltaStatistics.average,
        difference: difference(
          sourceDeltaStatistics.average,
          previousSourceDeltaStatistics.average,
        ),
      },
      {
        label: "ΔT plancher",
        unit: "°C",
        current:
          floorDeltaStatistics.average,
        previous:
          previousFloorDeltaStatistics.average,
        difference: difference(
          floorDeltaStatistics.average,
          previousFloorDeltaStatistics.average,
        ),
      },
      {
        label: "Taux de marche",
        unit: "%",
        current:
          visibleHistory.length > 0
            ? runtimeRatio
            : null,
        previous:
          previousRuntimeRatio,
        difference: difference(
          visibleHistory.length > 0
            ? runtimeRatio
            : null,
          previousRuntimeRatio,
        ),
      },
    ];

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

  const liveWindow =
    windowEndRatio >= 0.995;

  const zoomPercent =
    Math.round(
      windowSizeRatio * 100,
    );

  const visibleStartTimestamp =
    visibleHistory[0]?.timestamp ?? null;

  const visibleEndTimestamp =
    visibleHistory.at(-1)?.timestamp ?? null;

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

  const handleChartWheel =
    useCallback(
      (
        event: React.WheelEvent<
          SVGSVGElement
        >,
      ) => {
        if (periodHistory.length < 3) {
          return;
        }

        event.preventDefault();

        const bounds =
          event.currentTarget
            .getBoundingClientRect();

        const pointerRatio =
          clamp(
            (
              event.clientX -
              bounds.left
            ) /
              bounds.width,
            0,
            1,
          );

        const zoomFactor =
          event.deltaY > 0
            ? 1.18
            : 0.82;

        const previousSize =
          windowSizeRatio;

        const nextSize =
          clamp(
            previousSize *
              zoomFactor,
            0.1,
            1,
          );

        if (
          Math.abs(
            nextSize -
              previousSize,
          ) < 0.001
        ) {
          return;
        }

        const previousStart =
          windowEndRatio -
          previousSize;

        const focalPoint =
          previousStart +
          previousSize *
            pointerRatio;

        let nextStart =
          focalPoint -
          nextSize *
            pointerRatio;

        nextStart =
          clamp(
            nextStart,
            0,
            1 - nextSize,
          );

        setWindowSizeRatio(
          nextSize,
        );

        setWindowEndRatio(
          clamp(
            nextStart +
              nextSize,
            nextSize,
            1,
          ),
        );
      },
      [
        periodHistory.length,
        windowSizeRatio,
        windowEndRatio,
      ],
    );

  const updateZoom =
    (
      value: number,
    ) => {
      const nextSize =
        clamp(
          value / 100,
          0.1,
          1,
        );

      const previousStart =
        windowEndRatio -
        windowSizeRatio;

      const previousCenter =
        previousStart +
        windowSizeRatio / 2;

      const nextStart =
        clamp(
          previousCenter -
            nextSize / 2,
          0,
          1 - nextSize,
        );

      setWindowSizeRatio(
        nextSize,
      );

      setWindowEndRatio(
        clamp(
          nextStart +
            nextSize,
          nextSize,
          1,
        ),
      );
    };

  const moveWindow =
    (
      direction: "previous" | "next",
    ) => {
      const movement =
        windowSizeRatio * 0.65;

      const signedMovement =
        direction === "previous"
          ? -movement
          : movement;

      setWindowEndRatio(
        (current) =>
          clamp(
            current +
              signedMovement,
            windowSizeRatio,
            1,
          ),
      );
    };

  const returnToLive =
    () => {
      setWindowEndRatio(1);
      setCursorIndex(null);
    };

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

  const handleImportFile =
    async (
      file:
        File | null,
    ) => {
      if (!file) {
        return;
      }

      setImporting(true);
      setImportStatus(null);

      try {
        const content =
          await file.text();

        const extension =
          file.name
            .split(".")
            .at(-1)
            ?.toLowerCase();

        const imported =
          extension === "csv"
            ? parseCsvHistory(
                content,
              )
            : parseJsonHistory(
                content,
              );

        if (
          imported.length === 0
        ) {
          throw new Error(
            "Aucun point exploitable n’a été trouvé.",
          );
        }

        const updated =
          importMode === "replace"
            ? imported
                .sort(
                  (
                    left,
                    right,
                  ) =>
                    new Date(
                      left.timestamp,
                    ).getTime() -
                    new Date(
                      right.timestamp,
                    ).getTime(),
                )
                .slice(
                  -MAX_POINTS,
                )
            : mergeHistoryPoints(
                history,
                imported,
              );

        setHistory(updated);
        saveHistory(updated);

        const lastPoint =
          updated.at(-1);

        lastStoredAtRef.current =
          lastPoint
            ? new Date(
                lastPoint.timestamp,
              ).getTime()
            : 0;

        setWindowSizeRatio(1);
        setWindowEndRatio(1);
        setCursorIndex(null);

        setImportStatus({
          tone: "success",
          message:
            `${imported.length.toLocaleString(
              "fr-FR",
            )} point(s) importé(s). ` +
            `${updated.length.toLocaleString(
              "fr-FR",
            )} point(s) en mémoire.`,
        });
      } catch (importError) {
        setImportStatus({
          tone: "danger",
          message:
            importError instanceof Error
              ? importError.message
              : "Import impossible.",
        });
      } finally {
        setImporting(false);

        if (
          importInputRef.current
        ) {
          importInputRef.current.value =
            "";
        }
      }
    };

  const exportComparison = () => {
    if (
      visibleHistory.length === 0
    ) {
      return;
    }

    const payload = {
      exportedAt:
        new Date().toISOString(),

      currentPeriod: {
        start:
          visibleHistory[0]
            ?.timestamp ?? null,

        end:
          visibleHistory.at(-1)
            ?.timestamp ?? null,

        pointCount:
          visibleHistory.length,
      },

      previousPeriod: {
        start:
          previousHistory[0]
            ?.timestamp ?? null,

        end:
          previousHistory.at(-1)
            ?.timestamp ?? null,

        pointCount:
          previousHistory.length,
      },

      metrics:
        comparisonMetrics,
    };

    downloadTextFile(
      JSON.stringify(
        payload,
        null,
        2,
      ),
      `geocooling-comparison-${new Date()
        .toISOString()
        .replaceAll(
          ":",
          "-",
        )}.json`,
      "application/json;charset=utf-8",
    );
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

          <input
            ref={importInputRef}
            type="file"
            accept=".json,.csv,application/json,text/csv"
            className="gc-historian-import-input"
            onChange={(event) => {
              void handleImportFile(
                event.target.files?.[
                  0
                ] ?? null,
              );
            }}
          />

          <button
            type="button"
            onClick={() =>
              importInputRef.current
                ?.click()
            }
            disabled={importing}
          >
            {importing
              ? "Import…"
              : "Importer"}
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

      <section className="gc-historian-import-panel">
        <div>
          <span>
            RESTAURATION DE SESSION
          </span>

          <strong>
            Import JSON ou CSV
          </strong>

          <small>
            Les fichiers sont analysés localement
            dans le navigateur.
          </small>
        </div>

        <div className="gc-historian-import-mode">
          <button
            type="button"
            className={
              importMode === "merge"
                ? "is-active"
                : ""
            }
            onClick={() =>
              setImportMode(
                "merge",
              )
            }
          >
            Fusionner
          </button>

          <button
            type="button"
            className={
              importMode === "replace"
                ? "is-active"
                : ""
            }
            onClick={() =>
              setImportMode(
                "replace",
              )
            }
          >
            Remplacer
          </button>
        </div>

        {importStatus ? (
          <div
            className={`gc-historian-import-status is-${importStatus.tone}`}
            role="status"
          >
            <span>
              {importStatus.tone ===
              "success"
                ? "✓"
                : "!"}
            </span>

            <strong>
              {importStatus.message}
            </strong>
          </div>
        ) : (
          <div className="gc-historian-import-help">
            <span>i</span>

            <strong>
              Fusionner conserve les points existants.
              Remplacer efface la session courante.
            </strong>
          </div>
        )}
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

          <div className="gc-historian-enterprise-period-control">
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

            <span
              className={
                liveWindow
                  ? "gc-historian-window-state is-live"
                  : "gc-historian-window-state is-history"
              }
            >
              <i />

              {liveWindow
                ? "TEMPS RÉEL"
                : "HISTORIQUE"}
            </span>
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
                onWheel={
                  handleChartWheel
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

        <section className="gc-historian-enterprise-navigator">
          <header>
            <div>
              <span>
                FENÊTRE TEMPORELLE
              </span>

              <strong>
                {formatDateTime(
                  visibleStartTimestamp,
                )}
                {" → "}
                {formatDateTime(
                  visibleEndTimestamp,
                )}
              </strong>
            </div>

            <div className="gc-historian-enterprise-navigator__buttons">
              <button
                type="button"
                onClick={() =>
                  moveWindow(
                    "previous",
                  )
                }
                disabled={
                  windowEndRatio -
                    windowSizeRatio <=
                  0.001
                }
                title="Reculer dans l’historique"
              >
                ←
              </button>

              <button
                type="button"
                onClick={returnToLive}
                disabled={liveWindow}
              >
                Temps réel
              </button>

              <button
                type="button"
                onClick={() =>
                  moveWindow(
                    "next",
                  )
                }
                disabled={liveWindow}
                title="Avancer dans l’historique"
              >
                →
              </button>
            </div>
          </header>

          <div className="gc-historian-enterprise-navigator__controls">
            <label>
              <span>POSITION</span>

              <input
                type="range"
                min={
                  Math.round(
                    windowSizeRatio *
                      100,
                  )
                }
                max="100"
                step="1"
                value={
                  Math.round(
                    windowEndRatio *
                      100,
                  )
                }
                onChange={(event) =>
                  setWindowEndRatio(
                    clamp(
                      Number(
                        event.target
                          .value,
                      ) / 100,
                      windowSizeRatio,
                      1,
                    ),
                  )
                }
                disabled={
                  periodHistory.length <
                    3 ||
                  windowSizeRatio >=
                    0.999
                }
              />
            </label>

            <label>
              <span>
                ZOOM {zoomPercent} %
              </span>

              <input
                type="range"
                min="10"
                max="100"
                step="5"
                value={zoomPercent}
                onChange={(event) =>
                  updateZoom(
                    Number(
                      event.target.value,
                    ),
                  )
                }
                disabled={
                  periodHistory.length <
                  3
                }
              />
            </label>
          </div>

          <div className="gc-historian-enterprise-overview">
            <div
              className="gc-historian-enterprise-overview__window"
              style={{
                left: `${
                  (
                    windowEndRatio -
                    windowSizeRatio
                  ) * 100
                }%`,
                width: `${
                  windowSizeRatio *
                  100
                }%`,
              }}
            />

            <span>
              {formatTime(
                periodHistory[0]
                  ?.timestamp,
              )}
            </span>

            <span>
              {periodHistory.length.toLocaleString(
                "fr-FR",
              )}{" "}
              points
            </span>

            <span>
              {formatTime(
                periodHistory.at(-1)
                  ?.timestamp,
              )}
            </span>
          </div>

          <small>
            Utilisez la molette sur le graphique pour
            zoomer autour du curseur.
          </small>
        </section>

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

      <section className="gc-historian-comparison">
        <header>
          <div>
            <p className="gc-page-header__eyebrow">
              COMPARAISON TEMPORELLE
            </p>

            <h3>
              Fenêtre visible / période précédente
            </h3>
          </div>

          <div>
            <span>
              {previousHistory.length.toLocaleString(
                "fr-FR",
              )}{" "}
              points de référence
            </span>

            <button
              type="button"
              onClick={exportComparison}
              disabled={
                previousHistory.length === 0
              }
            >
              Exporter le rapport
            </button>
          </div>
        </header>

        {previousHistory.length === 0 ? (
          <div className="gc-historian-comparison__empty">
            <span>i</span>

            <div>
              <strong>
                Comparaison indisponible
              </strong>

              <small>
                Il n’existe pas encore suffisamment
                de données avant la fenêtre actuelle.
              </small>
            </div>
          </div>
        ) : (
          <div className="gc-historian-comparison__grid">
            {comparisonMetrics.map(
              (metric) => {
                const differenceValue =
                  metric.difference;

                const positive =
                  differenceValue !== null &&
                  (
                    metric.inversePositive
                      ? differenceValue < 0
                      : differenceValue > 0
                  );

                const negative =
                  differenceValue !== null &&
                  (
                    metric.inversePositive
                      ? differenceValue > 0
                      : differenceValue < 0
                  );

                return (
                  <article
                    key={metric.label}
                  >
                    <span>
                      {metric.label}
                    </span>

                    <div>
                      <section>
                        <small>
                          ACTUEL
                        </small>

                        <strong>
                          {formatNumber(
                            metric.current,
                          )}{" "}
                          {metric.unit}
                        </strong>
                      </section>

                      <section>
                        <small>
                          PRÉCÉDENT
                        </small>

                        <strong>
                          {formatNumber(
                            metric.previous,
                          )}{" "}
                          {metric.unit}
                        </strong>
                      </section>
                    </div>

                    <footer
                      className={
                        positive
                          ? "is-positive"
                          : negative
                            ? "is-negative"
                            : "is-neutral"
                      }
                    >
                      <span>
                        {differenceValue ===
                        null
                          ? "—"
                          : differenceValue >
                              0
                            ? "↗"
                            : differenceValue <
                                0
                              ? "↘"
                              : "→"}
                      </span>

                      <strong>
                        {differenceValue ===
                        null
                          ? "Non disponible"
                          : `${
                              differenceValue >
                              0
                                ? "+"
                                : ""
                            }${formatNumber(
                              differenceValue,
                            )} ${
                              metric.unit
                            }`}
                      </strong>
                    </footer>
                  </article>
                );
              },
            )}
          </div>
        )}

        <footer className="gc-historian-comparison__periods">
          <div>
            <span>
              FENÊTRE ACTUELLE
            </span>

            <strong>
              {formatDateTime(
                visibleHistory[0]
                  ?.timestamp,
              )}
              {" → "}
              {formatDateTime(
                visibleHistory.at(-1)
                  ?.timestamp,
              )}
            </strong>
          </div>

          <div>
            <span>
              FENÊTRE PRÉCÉDENTE
            </span>

            <strong>
              {formatDateTime(
                previousHistory[0]
                  ?.timestamp,
              )}
              {" → "}
              {formatDateTime(
                previousHistory.at(-1)
                  ?.timestamp,
              )}
            </strong>
          </div>
        </footer>
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
