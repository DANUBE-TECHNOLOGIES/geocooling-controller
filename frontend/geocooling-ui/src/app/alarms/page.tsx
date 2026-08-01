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

type AlarmSeverity =
  | "critical"
  | "warning"
  | "information";

type AlarmDefinition = {
  id: string;
  title: string;
  description: string;
  severity: AlarmSeverity;
  active: boolean;
  source: string;
  recommendation: string;
  value?: string;
};

type AlarmEvent = {
  eventId: string;
  alarmId: string;
  title: string;
  description: string;
  severity: AlarmSeverity;
  source: string;
  recommendation: string;
  value: string | null;
  startedAt: string;
  endedAt: string | null;
  acknowledgedAt: string | null;
  acknowledgedBy: string | null;
  lastSeenAt: string;
};

type AlarmFilter =
  | "active"
  | "unacknowledged"
  | "acknowledged"
  | "history"
  | "all";

type SeverityFilter =
  | "all"
  | AlarmSeverity;

type AlarmAnalytics = {
  totalEvents: number;
  activeEvents: number;
  closedEvents: number;
  acknowledgedEvents: number;
  averageAcknowledgementMs: number | null;
  averageResolutionMs: number | null;
  longestEventMs: number | null;
  acknowledgementRate: number;
  resolutionRate: number;
};

type AlarmOccurrence = {
  alarmId: string;
  title: string;
  source: string;
  severity: AlarmSeverity;
  count: number;
  totalDurationMs: number;
  averageDurationMs: number | null;
  lastOccurrenceAt: string;
};

type TimelineBucket = {
  label: string;
  start: number;
  end: number;
  critical: number;
  warning: number;
  information: number;
};

const STORAGE_KEY =
  "geocooling-ui-alarm-center-v1";

const MAX_EVENTS = 500;

function validNumber(
  value: number | null | undefined,
): value is number {
  return (
    typeof value === "number" &&
    Number.isFinite(value)
  );
}

function dewPoint(
  temperature: number | null | undefined,
  humidity: number | null | undefined,
): number | null {
  if (
    !validNumber(temperature) ||
    !validNumber(humidity) ||
    humidity <= 0 ||
    humidity > 100
  ) {
    return null;
  }

  const a = 17.62;
  const b = 243.12;

  const gamma =
    Math.log(humidity / 100) +
    (a * temperature) /
      (b + temperature);

  return (
    (b * gamma) /
    (a - gamma)
  );
}

function buildAlarms(
  snapshot: GeoCoolingSnapshot | null,
  connected: boolean,
  error: string | null,
): AlarmDefinition[] {
  const calculatedDewPoint =
    dewPoint(
      snapshot?.indoorTemperature,
      snapshot?.humidity,
    );

  const condensationMargin =
    calculatedDewPoint !== null &&
    validNumber(
      snapshot?.supplyTemperature,
    )
      ? snapshot.supplyTemperature -
        calculatedDewPoint
      : null;

  const hydraulicMismatch =
    snapshot !== null &&
    snapshot.pumpRunning !==
      snapshot.valveOpen;

  const missingSensors = [
    snapshot?.sourceInTemperature,
    snapshot?.sourceOutTemperature,
    snapshot?.supplyTemperature,
    snapshot?.returnTemperature,
  ].filter(
    (value) =>
      !validNumber(value),
  ).length;

  return [
    {
      id: "backend-offline",
      title:
        "Communication backend interrompue",
      description:
        error ||
        "L’interface ne reçoit plus de snapshot du contrôleur GeoCooling.",
      severity: "critical",
      active: !connected,
      source: "API GeoCooling",
      recommendation:
        "Vérifier le backend, le proxy Next.js et la connectivité réseau.",
    },
    {
      id: "safety-block",
      title:
        "Sécurité générale bloquante",
      description:
        "Le contrôleur indique que les conditions de sécurité ne sont pas validées.",
      severity: "critical",
      active:
        snapshot?.safetySafe === false,
      source: "Contrôleur",
      recommendation:
        "Maintenir la pompe et l’électrovanne à l’arrêt puis identifier la sécurité déclenchée.",
    },
    {
      id: "device-not-ready",
      title: "Matériel non prêt",
      description:
        "Le driver matériel ne déclare pas l’installation prête à fonctionner.",
      severity: "warning",
      active:
        snapshot?.deviceReady === false,
      source: "Driver matériel",
      recommendation:
        "Contrôler l’alimentation, le Waveshare, Modbus TCP et les relais configurés.",
    },
    {
      id: "hydraulic-mismatch",
      title:
        "Séquence hydraulique incohérente",
      description:
        "La pompe et l’électrovanne ne sont pas dans le même état.",
      severity: "warning",
      active: hydraulicMismatch,
      source: "Hydraulique",
      recommendation:
        "Vérifier la séquence de commande et les retours d’état des équipements.",
      value:
        snapshot
          ? `Pompe ${
              snapshot.pumpRunning
                ? "ON"
                : "OFF"
            } / Vanne ${
              snapshot.valveOpen
                ? "OUVERTE"
                : "FERMÉE"
            }`
          : undefined,
    },
    {
      id: "condensation-risk",
      title:
        "Risque de condensation",
      description:
        condensationMargin === null
          ? "La marge de condensation ne peut pas être calculée."
          : `La marge calculée est de ${condensationMargin.toFixed(
              1,
            )} °C.`,
      severity:
        condensationMargin !== null &&
        condensationMargin < 2
          ? "critical"
          : "warning",
      active:
        condensationMargin !== null &&
        condensationMargin < 3,
      source: "Thermique",
      recommendation:
        "Augmenter la température de départ ou suspendre le rafraîchissement.",
      value:
        condensationMargin === null
          ? undefined
          : `${condensationMargin.toFixed(
              1,
            )} °C`,
    },
    {
      id: "sensors-missing",
      title:
        "Télémétrie hydraulique incomplète",
      description:
        `${missingSensors} sonde(s) hydraulique(s) ne transmettent pas de valeur exploitable.`,
      severity: "warning",
      active: missingSensors > 0,
      source: "Instrumentation",
      recommendation:
        "Contrôler les DS18B20, le bus 1-Wire et la remontée du snapshot.",
      value:
        `${4 - missingSensors}/4 sondes`,
    },
    {
      id: "manual-mode",
      title: "Mode manuel actif",
      description:
        "Le système n’est pas piloté en mode automatique.",
      severity: "information",
      active:
        snapshot?.mode === "manual",
      source: "Stratégie",
      recommendation:
        "Vérifier que le maintien en mode manuel est volontaire.",
    },
    {
      id: "simulation-mode",
      title: "Mode simulation actif",
      description:
        "Les décisions peuvent ne pas commander les équipements physiques.",
      severity: "information",
      active:
        snapshot?.mode ===
        "simulation",
      source: "Stratégie",
      recommendation:
        "Ne pas considérer les états simulés comme une validation matérielle.",
    },
  ];
}

function createEventId(
  alarmId: string,
): string {
  return [
    alarmId,
    Date.now().toString(36),
    Math.random()
      .toString(36)
      .slice(2, 7),
  ].join("-");
}

function readStoredEvents(): AlarmEvent[] {
  if (
    typeof window === "undefined"
  ) {
    return [];
  }

  try {
    const raw =
      window.localStorage.getItem(
        STORAGE_KEY,
      );

    if (!raw) {
      return [];
    }

    const parsed =
      JSON.parse(raw);

    return Array.isArray(parsed)
      ? parsed.slice(-MAX_EVENTS)
      : [];
  } catch {
    return [];
  }
}

function saveEvents(
  events: AlarmEvent[],
): void {
  try {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify(
        events.slice(-MAX_EVENTS),
      ),
    );
  } catch (error) {
    console.error(
      "[Alarm Center] Sauvegarde impossible",
      error,
    );
  }
}

function synchronizeEvents(
  currentEvents: AlarmEvent[],
  definitions: AlarmDefinition[],
  now: string,
): AlarmEvent[] {
  const next =
    currentEvents.map(
      (event) => ({ ...event }),
    );

  definitions.forEach(
    (definition) => {
      const openEvent =
        [...next]
          .reverse()
          .find(
            (event) =>
              event.alarmId ===
                definition.id &&
              event.endedAt === null,
          );

      if (
        definition.active &&
        openEvent
      ) {
        openEvent.lastSeenAt = now;
        openEvent.description =
          definition.description;
        openEvent.severity =
          definition.severity;
        openEvent.value =
          definition.value ?? null;

        return;
      }

      if (
        definition.active &&
        !openEvent
      ) {
        next.push({
          eventId:
            createEventId(
              definition.id,
            ),
          alarmId: definition.id,
          title: definition.title,
          description:
            definition.description,
          severity:
            definition.severity,
          source: definition.source,
          recommendation:
            definition.recommendation,
          value:
            definition.value ?? null,
          startedAt: now,
          endedAt: null,
          acknowledgedAt: null,
          acknowledgedBy: null,
          lastSeenAt: now,
        });

        return;
      }

      if (
        !definition.active &&
        openEvent
      ) {
        openEvent.endedAt = now;
        openEvent.lastSeenAt = now;
      }
    },
  );

  return next
    .sort(
      (left, right) =>
        new Date(
          left.startedAt,
        ).getTime() -
        new Date(
          right.startedAt,
        ).getTime(),
    )
    .slice(-MAX_EVENTS);
}

function severityLabel(
  severity: AlarmSeverity,
): string {
  switch (severity) {
    case "critical":
      return "CRITIQUE";

    case "warning":
      return "AVERTISSEMENT";

    default:
      return "INFORMATION";
  }
}

function severityTone(
  severity: AlarmSeverity,
): "danger" | "warning" | "info" {
  switch (severity) {
    case "critical":
      return "danger";

    case "warning":
      return "warning";

    default:
      return "info";
  }
}

function formatDateTime(
  value: string | null,
): string {
  if (!value) {
    return "—";
  }

  const date =
    new Date(value);

  if (
    Number.isNaN(
      date.getTime(),
    )
  ) {
    return "—";
  }

  return date.toLocaleString(
    "fr-FR",
    {
      dateStyle: "short",
      timeStyle: "medium",
    },
  );
}

function millisecondsBetween(
  start: string | null,
  end: string | null,
): number | null {
  if (!start || !end) {
    return null;
  }

  const startTime =
    new Date(start).getTime();

  const endTime =
    new Date(end).getTime();

  if (
    !Number.isFinite(startTime) ||
    !Number.isFinite(endTime) ||
    endTime < startTime
  ) {
    return null;
  }

  return endTime - startTime;
}

function averageNumbers(
  values: number[],
): number | null {
  if (values.length === 0) {
    return null;
  }

  return (
    values.reduce(
      (total, value) =>
        total + value,
      0,
    ) / values.length
  );
}

function formatMetricDuration(
  milliseconds: number | null,
): string {
  if (milliseconds === null) {
    return "—";
  }

  const seconds =
    Math.max(
      0,
      Math.round(
        milliseconds / 1000,
      ),
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

  if (hours < 24) {
    return remainingMinutes > 0
      ? `${hours} h ${remainingMinutes} min`
      : `${hours} h`;
  }

  const days =
    Math.floor(hours / 24);

  const remainingHours =
    hours % 24;

  return `${days} j ${remainingHours} h`;
}

function calculateAnalytics(
  events: AlarmEvent[],
  now: number,
): AlarmAnalytics {
  const acknowledgementDurations =
    events
      .map((event) =>
        millisecondsBetween(
          event.startedAt,
          event.acknowledgedAt,
        ),
      )
      .filter(
        (
          duration,
        ): duration is number =>
          duration !== null,
      );

  const resolutionDurations =
    events
      .map((event) =>
        millisecondsBetween(
          event.startedAt,
          event.endedAt,
        ),
      )
      .filter(
        (
          duration,
        ): duration is number =>
          duration !== null,
      );

  const allDurations =
    events
      .map((event) => {
        const end =
          event.endedAt ??
          new Date(now).toISOString();

        return millisecondsBetween(
          event.startedAt,
          end,
        );
      })
      .filter(
        (
          duration,
        ): duration is number =>
          duration !== null,
      );

  const acknowledgedEvents =
    events.filter(
      (event) =>
        event.acknowledgedAt !==
        null,
    ).length;

  const closedEvents =
    events.filter(
      (event) =>
        event.endedAt !== null,
    ).length;

  return {
    totalEvents:
      events.length,

    activeEvents:
      events.length -
      closedEvents,

    closedEvents,

    acknowledgedEvents,

    averageAcknowledgementMs:
      averageNumbers(
        acknowledgementDurations,
      ),

    averageResolutionMs:
      averageNumbers(
        resolutionDurations,
      ),

    longestEventMs:
      allDurations.length > 0
        ? Math.max(
            ...allDurations,
          )
        : null,

    acknowledgementRate:
      events.length === 0
        ? 100
        : Math.round(
            (
              acknowledgedEvents /
              events.length
            ) *
              100,
          ),

    resolutionRate:
      events.length === 0
        ? 100
        : Math.round(
            (
              closedEvents /
              events.length
            ) *
              100,
          ),
  };
}

function calculateOccurrences(
  events: AlarmEvent[],
  now: number,
): AlarmOccurrence[] {
  const groups =
    new Map<
      string,
      AlarmOccurrence & {
        durations: number[];
      }
    >();

  events.forEach((event) => {
    const duration =
      millisecondsBetween(
        event.startedAt,
        event.endedAt ??
          new Date(now).toISOString(),
      );

    const existing =
      groups.get(
        event.alarmId,
      );

    if (existing) {
      existing.count += 1;

      if (duration !== null) {
        existing.durations.push(
          duration,
        );

        existing.totalDurationMs +=
          duration;
      }

      if (
        new Date(
          event.startedAt,
        ).getTime() >
        new Date(
          existing.lastOccurrenceAt,
        ).getTime()
      ) {
        existing.lastOccurrenceAt =
          event.startedAt;

        existing.severity =
          event.severity;
      }

      return;
    }

    groups.set(
      event.alarmId,
      {
        alarmId:
          event.alarmId,

        title:
          event.title,

        source:
          event.source,

        severity:
          event.severity,

        count: 1,

        totalDurationMs:
          duration ?? 0,

        averageDurationMs:
          duration,

        lastOccurrenceAt:
          event.startedAt,

        durations:
          duration === null
            ? []
            : [duration],
      },
    );
  });

  return Array.from(
    groups.values(),
  )
    .map((occurrence) => ({
      alarmId:
        occurrence.alarmId,

      title:
        occurrence.title,

      source:
        occurrence.source,

      severity:
        occurrence.severity,

      count:
        occurrence.count,

      totalDurationMs:
        occurrence.totalDurationMs,

      averageDurationMs:
        averageNumbers(
          occurrence.durations,
        ),

      lastOccurrenceAt:
        occurrence.lastOccurrenceAt,
    }))
    .sort(
      (left, right) =>
        right.count -
          left.count ||
        right.totalDurationMs -
          left.totalDurationMs,
    );
}

function buildTimeline(
  events: AlarmEvent[],
  now: number,
): TimelineBucket[] {
  const bucketCount = 12;
  const horizonMs =
    24 * 60 * 60 * 1000;

  const bucketDuration =
    horizonMs /
    bucketCount;

  const start =
    now - horizonMs;

  return Array.from(
    {
      length:
        bucketCount,
    },
    (_, index) => {
      const bucketStart =
        start +
        index *
          bucketDuration;

      const bucketEnd =
        bucketStart +
        bucketDuration;

      const bucketEvents =
        events.filter(
          (event) => {
            const eventStart =
              new Date(
                event.startedAt,
              ).getTime();

            return (
              eventStart >=
                bucketStart &&
              eventStart <
                bucketEnd
            );
          },
        );

      const label =
        new Date(
          bucketStart,
        ).toLocaleTimeString(
          "fr-FR",
          {
            hour: "2-digit",
            minute: "2-digit",
          },
        );

      return {
        label,
        start:
          bucketStart,
        end:
          bucketEnd,

        critical:
          bucketEvents.filter(
            (event) =>
              event.severity ===
              "critical",
          ).length,

        warning:
          bucketEvents.filter(
            (event) =>
              event.severity ===
              "warning",
          ).length,

        information:
          bucketEvents.filter(
            (event) =>
              event.severity ===
              "information",
          ).length,
      };
    },
  );
}

function escapeCsvValue(
  value: unknown,
): string {
  return `"${String(
    value ?? "",
  ).replaceAll(
    '"',
    '""',
  )}"`;
}

function downloadTextFile(
  content: string,
  filename: string,
  mimeType: string,
): void {
  const blob =
    new Blob(
      [content],
      {
        type:
          mimeType,
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

function formatDuration(
  start: string,
  end: string | null,
  now: number,
): string {
  const startTime =
    new Date(start).getTime();

  const endTime =
    end
      ? new Date(end).getTime()
      : now;

  if (
    !Number.isFinite(startTime) ||
    !Number.isFinite(endTime)
  ) {
    return "—";
  }

  const seconds =
    Math.max(
      0,
      Math.floor(
        (endTime - startTime) /
          1000,
      ),
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

  if (hours < 24) {
    return remainingMinutes > 0
      ? `${hours} h ${remainingMinutes} min`
      : `${hours} h`;
  }

  const days =
    Math.floor(hours / 24);

  const remainingHours =
    hours % 24;

  return `${days} j ${remainingHours} h`;
}

export default function AlarmsPage() {
  const {
    snapshot,
    loading,
    refreshing,
    error,
    lastUpdate,
    responseTime,
    refresh,
  } = useGeoCooling();

  const [events, setEvents] =
    useState<AlarmEvent[]>([]);

  const [initialized, setInitialized] =
    useState(false);

  const [filter, setFilter] =
    useState<AlarmFilter>("active");

  const [
    severityFilter,
    setSeverityFilter,
  ] =
    useState<SeverityFilter>("all");

  const [search, setSearch] =
    useState("");

  const [clock, setClock] =
    useState(Date.now());

  const connected =
    Boolean(snapshot && !error);

  const definitions =
    useMemo(
      () =>
        buildAlarms(
          snapshot,
          connected,
          error,
        ),
      [
        snapshot,
        connected,
        error,
      ],
    );

  useEffect(() => {
    setEvents(
      readStoredEvents(),
    );

    setInitialized(true);
  }, []);

  useEffect(() => {
    const timer =
      window.setInterval(
        () => {
          setClock(Date.now());
        },
        1000,
      );

    return () => {
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    if (!initialized) {
      return;
    }

    const now =
      new Date().toISOString();

    setEvents((current) => {
      const updated =
        synchronizeEvents(
          current,
          definitions,
          now,
        );

      saveEvents(updated);

      return updated;
    });
  }, [
    definitions,
    initialized,
  ]);

  const activeEvents =
    events.filter(
      (event) =>
        event.endedAt === null,
    );

  const unacknowledgedEvents =
    activeEvents.filter(
      (event) =>
        event.acknowledgedAt ===
        null,
    );

  const criticalCount =
    activeEvents.filter(
      (event) =>
        event.severity ===
        "critical",
    ).length;

  const warningCount =
    activeEvents.filter(
      (event) =>
        event.severity ===
        "warning",
    ).length;

  const informationCount =
    activeEvents.filter(
      (event) =>
        event.severity ===
        "information",
    ).length;

  const analytics =
    useMemo(
      () =>
        calculateAnalytics(
          events,
          clock,
        ),
      [
        events,
        clock,
      ],
    );

  const occurrences =
    useMemo(
      () =>
        calculateOccurrences(
          events,
          clock,
        ),
      [
        events,
        clock,
      ],
    );

  const timeline =
    useMemo(
      () =>
        buildTimeline(
          events,
          clock,
        ),
      [
        events,
        clock,
      ],
    );

  const maximumTimelineValue =
    Math.max(
      1,
      ...timeline.map(
        (bucket) =>
          bucket.critical +
          bucket.warning +
          bucket.information,
      ),
    );

  const filteredEvents =
    useMemo(() => {
      const normalizedSearch =
        search
          .trim()
          .toLowerCase();

      return [...events]
        .reverse()
        .filter((event) => {
          switch (filter) {
            case "active":
              if (
                event.endedAt !== null
              ) {
                return false;
              }
              break;

            case "unacknowledged":
              if (
                event.endedAt !== null ||
                event.acknowledgedAt !==
                  null
              ) {
                return false;
              }
              break;

            case "acknowledged":
              if (
                event.acknowledgedAt ===
                null
              ) {
                return false;
              }
              break;

            case "history":
              if (
                event.endedAt === null
              ) {
                return false;
              }
              break;

            case "all":
              break;
          }

          if (
            severityFilter !==
              "all" &&
            event.severity !==
              severityFilter
          ) {
            return false;
          }

          if (!normalizedSearch) {
            return true;
          }

          return [
            event.title,
            event.description,
            event.source,
            event.recommendation,
            event.value ?? "",
          ].some((value) =>
            value
              .toLowerCase()
              .includes(
                normalizedSearch,
              ),
          );
        });
    }, [
      events,
      filter,
      severityFilter,
      search,
    ]);

  const acknowledgeEvent =
    (eventId: string) => {
      const now =
        new Date().toISOString();

      setEvents((current) => {
        const updated =
          current.map((event) =>
            event.eventId ===
            eventId
              ? {
                  ...event,
                  acknowledgedAt:
                    event.acknowledgedAt ??
                    now,
                  acknowledgedBy:
                    event.acknowledgedBy ??
                    "Opérateur local",
                }
              : event,
          );

        saveEvents(updated);

        return updated;
      });
    };

  const acknowledgeAll = () => {
    const now =
      new Date().toISOString();

    setEvents((current) => {
      const updated =
        current.map((event) =>
          event.endedAt === null &&
          event.acknowledgedAt ===
            null
            ? {
                ...event,
                acknowledgedAt: now,
                acknowledgedBy:
                  "Opérateur local",
              }
            : event,
        );

      saveEvents(updated);

      return updated;
    });
  };

  const exportCsv = () => {
    if (
      filteredEvents.length === 0
    ) {
      return;
    }

    const header = [
      "event_id",
      "alarm_id",
      "severity",
      "status",
      "acknowledged",
      "source",
      "title",
      "description",
      "value",
      "started_at",
      "ended_at",
      "duration_seconds",
      "acknowledged_at",
      "acknowledged_by",
      "recommendation",
    ];

    const rows =
      filteredEvents.map(
        (event) => {
          const duration =
            millisecondsBetween(
              event.startedAt,
              event.endedAt ??
                new Date(
                  clock,
                ).toISOString(),
            );

          return [
            event.eventId,
            event.alarmId,
            event.severity,
            event.endedAt === null
              ? "active"
              : "closed",
            event.acknowledgedAt !==
              null,
            event.source,
            event.title,
            event.description,
            event.value ?? "",
            event.startedAt,
            event.endedAt ?? "",
            duration === null
              ? ""
              : Math.round(
                  duration /
                    1000,
                ),
            event.acknowledgedAt ??
              "",
            event.acknowledgedBy ??
              "",
            event.recommendation,
          ];
        },
      );

    const csv =
      [
        header,
        ...rows,
      ]
        .map(
          (row) =>
            row
              .map(
                escapeCsvValue,
              )
              .join(";"),
        )
        .join("\n");

    downloadTextFile(
      csv,
      `geocooling-alarm-events-${new Date()
        .toISOString()
        .replaceAll(
          ":",
          "-",
        )}.csv`,
      "text/csv;charset=utf-8",
    );
  };

  const exportJson = () => {
    if (
      filteredEvents.length === 0
    ) {
      return;
    }

    const payload = {
      exportedAt:
        new Date().toISOString(),

      filters: {
        state:
          filter,

        severity:
          severityFilter,

        search,
      },

      analytics,

      occurrences,

      timeline,

      events:
        filteredEvents,
    };

    downloadTextFile(
      JSON.stringify(
        payload,
        null,
        2,
      ),
      `geocooling-alarm-report-${new Date()
        .toISOString()
        .replaceAll(
          ":",
          "-",
        )}.json`,
      "application/json;charset=utf-8",
    );
  };

  const clearClosedHistory =
    () => {
      setEvents((current) => {
        const updated =
          current.filter(
            (event) =>
              event.endedAt === null,
          );

        saveEvents(updated);

        return updated;
      });
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
            ALARM CENTER ENTERPRISE
          </p>

          <h2>
            Alarmes & événements
          </h2>

          <p>
            Cycle de vie local des alarmes,
            acquittement opérateur, durée,
            historique et filtrage des événements.
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
              activeEvents.length ===
              0
                ? "SYSTÈME NORMAL"
                : `${activeEvents.length} ACTIVE(S)`
            }
            tone={
              criticalCount > 0
                ? "danger"
                : warningCount > 0
                  ? "warning"
                  : activeEvents.length >
                      0
                    ? "info"
                    : "success"
            }
            pulse={
              criticalCount > 0
            }
          />
        </div>
      </section>

      <section className="gc-alarm-center-banner">
        <div
          className={
            criticalCount > 0
              ? "is-critical"
              : warningCount > 0
                ? "is-warning"
                : activeEvents.length >
                    0
                  ? "is-information"
                  : "is-normal"
          }
        >
          <span />
        </div>

        <div>
          <strong>
            {criticalCount > 0
              ? "Intervention immédiate requise"
              : warningCount > 0
                ? "Surveillance opérateur nécessaire"
                : activeEvents.length >
                    0
                  ? "Information d’exploitation active"
                  : "Aucune anomalie active"}
          </strong>

          <small>
            {unacknowledgedEvents.length >
            0
              ? `${unacknowledgedEvents.length} événement(s) non acquitté(s)`
              : "Tous les événements actifs sont acquittés"}
          </small>
        </div>

        <button
          type="button"
          onClick={acknowledgeAll}
          disabled={
            unacknowledgedEvents.length ===
            0
          }
        >
          Acquitter toutes
        </button>
      </section>

      <section className="gc-alarm-center-kpis">
        <article className="is-critical">
          <span>CRITIQUES ACTIVES</span>
          <strong>
            {criticalCount}
          </strong>
          <small>
            Intervention immédiate
          </small>
        </article>

        <article className="is-warning">
          <span>AVERTISSEMENTS</span>
          <strong>
            {warningCount}
          </strong>
          <small>
            Surveillance nécessaire
          </small>
        </article>

        <article className="is-information">
          <span>INFORMATIONS</span>
          <strong>
            {informationCount}
          </strong>
          <small>
            État particulier
          </small>
        </article>

        <article className="is-unacknowledged">
          <span>NON ACQUITTÉES</span>
          <strong>
            {
              unacknowledgedEvents.length
            }
          </strong>
          <small>
            Action opérateur attendue
          </small>
        </article>

        <article>
          <span>HISTORIQUE</span>
          <strong>
            {
              events.filter(
                (event) =>
                  event.endedAt !==
                  null,
              ).length
            }
          </strong>
          <small>
            Événements terminés
          </small>
        </article>
      </section>

      <section className="gc-alarm-center-toolbar">
        <div className="gc-alarm-center-tabs">
          {[
            ["active", "Actives"],
            [
              "unacknowledged",
              "Non acquittées",
            ],
            [
              "acknowledged",
              "Acquittées",
            ],
            ["history", "Historique"],
            ["all", "Toutes"],
          ].map(
            ([value, label]) => (
              <button
                key={value}
                type="button"
                className={
                  filter === value
                    ? "is-active"
                    : ""
                }
                onClick={() =>
                  setFilter(
                    value as AlarmFilter,
                  )
                }
              >
                {label}
              </button>
            ),
          )}
        </div>

        <div className="gc-alarm-center-filters">
          <select
            value={severityFilter}
            onChange={(event) =>
              setSeverityFilter(
                event.target
                  .value as SeverityFilter,
              )
            }
            aria-label="Filtrer par criticité"
          >
            <option value="all">
              Toutes les criticités
            </option>

            <option value="critical">
              Critiques
            </option>

            <option value="warning">
              Avertissements
            </option>

            <option value="information">
              Informations
            </option>
          </select>

          <input
            type="search"
            value={search}
            onChange={(event) =>
              setSearch(
                event.target.value,
              )
            }
            placeholder="Rechercher une alarme…"
          />

          <button
            type="button"
            onClick={exportCsv}
            disabled={
              filteredEvents.length ===
              0
            }
          >
            Export CSV
          </button>

          <button
            type="button"
            onClick={exportJson}
            disabled={
              filteredEvents.length ===
              0
            }
          >
            Export JSON
          </button>

          <button
            type="button"
            className="is-danger"
            onClick={
              clearClosedHistory
            }
            disabled={
              !events.some(
                (event) =>
                  event.endedAt !==
                  null,
              )
            }
          >
            Purger l’historique
          </button>
        </div>
      </section>

      <section className="gc-alarm-center-table-panel">
        <header>
          <div>
            <p className="gc-page-header__eyebrow">
              JOURNAL DES ÉVÉNEMENTS
            </p>

            <h3>
              {filteredEvents.length} événement(s)
            </h3>
          </div>

          <span>
            Conservation locale :
            {" "}
            {MAX_EVENTS} événements
          </span>
        </header>

        {filteredEvents.length === 0 ? (
          <div className="gc-alarm-center-empty">
            <div aria-hidden="true">
              ✓
            </div>

            <strong>
              Aucun événement correspondant
            </strong>

            <p>
              Modifiez les filtres ou attendez
              l’apparition d’une nouvelle condition.
            </p>
          </div>
        ) : (
          <div className="gc-alarm-center-list">
            {filteredEvents.map(
              (event) => {
                const active =
                  event.endedAt ===
                  null;

                const acknowledged =
                  event.acknowledgedAt !==
                  null;

                return (
                  <article
                    key={event.eventId}
                    className={`gc-alarm-center-event is-${event.severity} ${
                      active
                        ? "is-active"
                        : "is-ended"
                    } ${
                      acknowledged
                        ? "is-acknowledged"
                        : "is-unacknowledged"
                    }`}
                  >
                    <div className="gc-alarm-center-event__priority">
                      <span />
                    </div>

                    <div className="gc-alarm-center-event__main">
                      <header>
                        <div>
                          <div className="gc-alarm-center-event__meta">
                            <span>
                              {event.source}
                            </span>

                            <i>•</i>

                            <strong>
                              {active
                                ? "ACTIVE"
                                : "TERMINÉE"}
                            </strong>

                            {acknowledged ? (
                              <>
                                <i>•</i>

                                <b>
                                  ACQUITTÉE
                                </b>
                              </>
                            ) : null}
                          </div>

                          <h3>
                            {event.title}
                          </h3>
                        </div>

                        <StatusBadge
                          label={
                            severityLabel(
                              event.severity,
                            )
                          }
                          tone={
                            severityTone(
                              event.severity,
                            )
                          }
                          pulse={
                            active &&
                            !acknowledged &&
                            event.severity ===
                              "critical"
                          }
                        />
                      </header>

                      <p>
                        {
                          event.description
                        }
                      </p>

                      {event.value ? (
                        <div className="gc-alarm-center-event__value">
                          <span>
                            VALEUR
                          </span>

                          <strong>
                            {event.value}
                          </strong>
                        </div>
                      ) : null}

                      <div className="gc-alarm-center-event__recommendation">
                        <span>
                          RECOMMANDATION
                        </span>

                        <strong>
                          {
                            event.recommendation
                          }
                        </strong>
                      </div>
                    </div>

                    <aside className="gc-alarm-center-event__timeline">
                      <div>
                        <span>
                          APPARITION
                        </span>

                        <strong>
                          {formatDateTime(
                            event.startedAt,
                          )}
                        </strong>
                      </div>

                      <div>
                        <span>
                          DURÉE
                        </span>

                        <strong>
                          {formatDuration(
                            event.startedAt,
                            event.endedAt,
                            clock,
                          )}
                        </strong>
                      </div>

                      <div>
                        <span>
                          FIN
                        </span>

                        <strong>
                          {formatDateTime(
                            event.endedAt,
                          )}
                        </strong>
                      </div>

                      <div>
                        <span>
                          ACQUITTEMENT
                        </span>

                        <strong>
                          {formatDateTime(
                            event.acknowledgedAt,
                          )}
                        </strong>
                      </div>

                      {!acknowledged &&
                      active ? (
                        <button
                          type="button"
                          onClick={() =>
                            acknowledgeEvent(
                              event.eventId,
                            )
                          }
                        >
                          ACK
                        </button>
                      ) : (
                        <div className="gc-alarm-center-event__ack">
                          <span>✓</span>

                          <strong>
                            {event.acknowledgedBy ??
                              (active
                                ? "Acquittée"
                                : "Terminée")}
                          </strong>
                        </div>
                      )}
                    </aside>
                  </article>
                );
              },
            )}
          </div>
        )}
      </section>

      <section className="gc-alarm-analytics">
        <header>
          <div>
            <p className="gc-page-header__eyebrow">
              ANALYSE DE PERFORMANCE
            </p>

            <h3>
              Indicateurs de traitement
            </h3>
          </div>

          <span>
            {
              analytics.totalEvents
            } événement(s) analysé(s)
          </span>
        </header>

        <div className="gc-alarm-analytics__kpis">
          <article>
            <span>
              MTTA
            </span>

            <strong>
              {formatMetricDuration(
                analytics
                  .averageAcknowledgementMs,
              )}
            </strong>

            <small>
              Délai moyen avant acquittement
            </small>
          </article>

          <article>
            <span>
              MTTR
            </span>

            <strong>
              {formatMetricDuration(
                analytics
                  .averageResolutionMs,
              )}
            </strong>

            <small>
              Durée moyenne avant résolution
            </small>
          </article>

          <article>
            <span>
              PLUS LONG ÉVÉNEMENT
            </span>

            <strong>
              {formatMetricDuration(
                analytics
                  .longestEventMs,
              )}
            </strong>

            <small>
              Actif ou terminé
            </small>
          </article>

          <article>
            <span>
              TAUX D’ACQUITTEMENT
            </span>

            <strong>
              {
                analytics
                  .acknowledgementRate
              } %
            </strong>

            <small>
              Événements pris en compte
            </small>
          </article>

          <article>
            <span>
              TAUX DE RÉSOLUTION
            </span>

            <strong>
              {
                analytics
                  .resolutionRate
              } %
            </strong>

            <small>
              Événements revenus à la normale
            </small>
          </article>
        </div>

        <div className="gc-alarm-analytics__layout">
          <article className="gc-alarm-timeline">
            <header>
              <div>
                <span>
                  CHRONOLOGIE 24 HEURES
                </span>

                <strong>
                  Apparitions par tranche de 2 heures
                </strong>
              </div>

              <div className="gc-alarm-timeline__legend">
                <span className="is-critical">
                  <i />
                  Critique
                </span>

                <span className="is-warning">
                  <i />
                  Avertissement
                </span>

                <span className="is-information">
                  <i />
                  Information
                </span>
              </div>
            </header>

            <div className="gc-alarm-timeline__chart">
              {timeline.map(
                (bucket) => {
                  const total =
                    bucket.critical +
                    bucket.warning +
                    bucket.information;

                  return (
                    <article
                      key={
                        bucket.start
                      }
                      title={`${bucket.label} — ${total} événement(s)`}
                    >
                      <div>
                        <span
                          className="is-critical"
                          style={{
                            height: `${
                              (
                                bucket.critical /
                                maximumTimelineValue
                              ) *
                              100
                            }%`,
                          }}
                        />

                        <span
                          className="is-warning"
                          style={{
                            height: `${
                              (
                                bucket.warning /
                                maximumTimelineValue
                              ) *
                              100
                            }%`,
                          }}
                        />

                        <span
                          className="is-information"
                          style={{
                            height: `${
                              (
                                bucket.information /
                                maximumTimelineValue
                              ) *
                              100
                            }%`,
                          }}
                        />
                      </div>

                      <strong>
                        {total}
                      </strong>

                      <small>
                        {
                          bucket.label
                        }
                      </small>
                    </article>
                  );
                },
              )}
            </div>
          </article>

          <article className="gc-alarm-recurrence">
            <header>
              <div>
                <span>
                  RÉCURRENCE
                </span>

                <strong>
                  Alarmes les plus fréquentes
                </strong>
              </div>

              <b>
                {
                  occurrences.length
                } type(s)
              </b>
            </header>

            {occurrences.length ===
            0 ? (
              <div className="gc-alarm-recurrence__empty">
                Aucun événement enregistré.
              </div>
            ) : (
              <div className="gc-alarm-recurrence__list">
                {occurrences
                  .slice(0, 8)
                  .map(
                    (
                      occurrence,
                      index,
                    ) => (
                      <article
                        key={
                          occurrence.alarmId
                        }
                      >
                        <span>
                          {String(
                            index + 1,
                          ).padStart(
                            2,
                            "0",
                          )}
                        </span>

                        <div>
                          <strong>
                            {
                              occurrence.title
                            }
                          </strong>

                          <small>
                            {
                              occurrence.source
                            }
                            {" · "}
                            Dernière :
                            {" "}
                            {formatDateTime(
                              occurrence.lastOccurrenceAt,
                            )}
                          </small>
                        </div>

                        <section>
                          <strong>
                            {
                              occurrence.count
                            }×
                          </strong>

                          <small>
                            Moy.
                            {" "}
                            {formatMetricDuration(
                              occurrence.averageDurationMs,
                            )}
                          </small>
                        </section>
                      </article>
                    ),
                  )}
              </div>
            )}
          </article>
        </div>
      </section>

      <section className="gc-alarm-center-matrix">
        <header>
          <div>
            <p className="gc-page-header__eyebrow">
              MATRICE DE SURVEILLANCE
            </p>

            <h3>
              Règles évaluées en temps réel
            </h3>
          </div>

          <span>
            {definitions.length} règles
          </span>
        </header>

        <div>
          {definitions.map(
            (definition) => (
              <article
                key={definition.id}
                className={
                  definition.active
                    ? `is-${definition.severity}`
                    : "is-clear"
                }
              >
                <span>
                  {definition.active
                    ? "!"
                    : "✓"}
                </span>

                <div>
                  <strong>
                    {definition.title}
                  </strong>

                  <small>
                    {definition.active
                      ? severityLabel(
                          definition.severity,
                        )
                      : "CONTRÔLE VALIDÉ"}
                  </small>
                </div>
              </article>
            ),
          )}
        </div>
      </section>

      {loading && !snapshot ? (
        <section className="gc-loading-state">
          <div className="gc-loading-spinner" />

          <div>
            <strong>
              Initialisation de l’Alarm Center…
            </strong>

            <span>
              Lecture du premier snapshot.
            </span>
          </div>
        </section>
      ) : null}
    </AppShell>
  );
}
