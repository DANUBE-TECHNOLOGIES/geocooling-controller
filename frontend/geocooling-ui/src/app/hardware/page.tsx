"use client";

import Link from "next/link";
import {
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { AppShell } from "@/components/layout/AppShell";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useGeoCooling } from "@/hooks/useGeoCooling";
import type { GeoCoolingSnapshot } from "@/types/geocooling";

type HealthTone =
  | "good"
  | "warning"
  | "critical"
  | "unknown";

type ChainNode = {
  id: string;
  label: string;
  description: string;
  value: string;
  tone: HealthTone;
  source: "measured" | "derived" | "unavailable";
};

type SensorNode = {
  id: string;
  label: string;
  description: string;
  value: number | null | undefined;
};

type CheckNode = {
  id: string;
  label: string;
  detail: string;
  tone: HealthTone;
};

type DiagnosticState = {
  connected: boolean;
  deviceReady: boolean | null;
  safetySafe: boolean | null;
  pumpRunning: boolean;
  valveOpen: boolean;
  availableSensors: number;
};

type DiagnosticEventType =
  | "communication"
  | "device"
  | "safety"
  | "pump"
  | "valve"
  | "sensors";

type DiagnosticEvent = {
  id: string;
  type: DiagnosticEventType;
  label: string;
  previousValue: string;
  currentValue: string;
  occurredAt: string;
  severity: HealthTone;
};

type AvailabilitySample = {
  timestamp: string;
  connected: boolean;
  responseTime: number;
  deviceReady: boolean | null;
};

type LatencyStatistics = {
  count: number;
  minimum: number | null;
  maximum: number | null;
  average: number | null;
};

function validNumber(
  value: number | null | undefined,
): value is number {
  return (
    typeof value === "number" &&
    Number.isFinite(value)
  );
}

function temperature(
  value: number | null | undefined,
): string {
  return validNumber(value)
    ? `${value.toFixed(1)} °C`
    : "Non disponible";
}

function toneLabel(
  tone: HealthTone,
): string {
  switch (tone) {
    case "good":
      return "OPÉRATIONNEL";

    case "warning":
      return "DÉGRADÉ";

    case "critical":
      return "DÉFAUT";

    default:
      return "INCONNU";
  }
}

function toneClass(
  tone: HealthTone,
): string {
  return `is-${tone}`;
}

function latencyTone(
  responseTime: number,
): HealthTone {
  if (responseTime <= 0) {
    return "unknown";
  }

  if (responseTime < 500) {
    return "good";
  }

  if (responseTime < 1500) {
    return "warning";
  }

  return "critical";
}

function deviceTone(
  snapshot: GeoCoolingSnapshot | null,
): HealthTone {
  if (!snapshot) {
    return "critical";
  }

  if (snapshot.deviceReady === true) {
    return "good";
  }

  if (snapshot.deviceReady === false) {
    return "critical";
  }

  return "unknown";
}

function safetyTone(
  snapshot: GeoCoolingSnapshot | null,
): HealthTone {
  if (!snapshot) {
    return "unknown";
  }

  if (snapshot.safetySafe === true) {
    return "good";
  }

  if (snapshot.safetySafe === false) {
    return "critical";
  }

  return "unknown";
}

function outputTone(
  value: boolean | null | undefined,
  available: boolean,
): HealthTone {
  if (!available) {
    return "unknown";
  }

  return value
    ? "good"
    : "warning";
}

function sourceLabel(
  source: ChainNode["source"],
): string {
  switch (source) {
    case "measured":
      return "MESURÉ";

    case "derived":
      return "DÉDUIT";

    default:
      return "NON EXPOSÉ";
  }
}

const DIAGNOSTIC_STORAGE_KEY =
  "geocooling-ui-hardware-diagnostics-v1";

const AVAILABILITY_STORAGE_KEY =
  "geocooling-ui-hardware-availability-v1";

const MAX_DIAGNOSTIC_EVENTS = 300;
const MAX_AVAILABILITY_SAMPLES = 3_600;

function createDiagnosticEventId(): string {
  return [
    "HW",
    Date.now().toString(36),
    Math.random()
      .toString(36)
      .slice(2, 7),
  ].join("-");
}

function booleanLabel(
  value: boolean | null,
  active: string,
  inactive: string,
): string {
  if (value === null) {
    return "INCONNU";
  }

  return value
    ? active
    : inactive;
}

function diagnosticStateFromValues(
  connected: boolean,
  snapshot: GeoCoolingSnapshot | null,
  availableSensors: number,
): DiagnosticState {
  return {
    connected,
    deviceReady:
      snapshot?.deviceReady ?? null,
    safetySafe:
      snapshot?.safetySafe ?? null,
    pumpRunning:
      snapshot?.pumpRunning ?? false,
    valveOpen:
      snapshot?.valveOpen ?? false,
    availableSensors,
  };
}

function readStoredArray<T>(
  key: string,
): T[] {
  if (
    typeof window === "undefined"
  ) {
    return [];
  }

  try {
    const raw =
      window.localStorage.getItem(
        key,
      );

    if (!raw) {
      return [];
    }

    const parsed =
      JSON.parse(raw);

    return Array.isArray(parsed)
      ? parsed
      : [];
  } catch {
    return [];
  }
}

function saveStoredArray<T>(
  key: string,
  values: T[],
): void {
  try {
    window.localStorage.setItem(
      key,
      JSON.stringify(values),
    );
  } catch (error) {
    console.error(
      "[Hardware Diagnostics] Sauvegarde impossible",
      error,
    );
  }
}

function severityForTransition(
  type: DiagnosticEventType,
  state: DiagnosticState,
): HealthTone {
  switch (type) {
    case "communication":
      return state.connected
        ? "good"
        : "critical";

    case "device":
      return state.deviceReady === true
        ? "good"
        : state.deviceReady === false
          ? "critical"
          : "unknown";

    case "safety":
      return state.safetySafe === true
        ? "good"
        : state.safetySafe === false
          ? "critical"
          : "unknown";

    case "sensors":
      return state.availableSensors === 4
        ? "good"
        : state.availableSensors > 0
          ? "warning"
          : "critical";

    case "pump":
    case "valve":
      return "warning";
  }
}

function buildDiagnosticEvents(
  previous: DiagnosticState,
  current: DiagnosticState,
): DiagnosticEvent[] {
  const now =
    new Date().toISOString();

  const events: DiagnosticEvent[] = [];

  const push = (
    type: DiagnosticEventType,
    label: string,
    previousValue: string,
    currentValue: string,
  ) => {
    events.push({
      id:
        createDiagnosticEventId(),
      type,
      label,
      previousValue,
      currentValue,
      occurredAt: now,
      severity:
        severityForTransition(
          type,
          current,
        ),
    });
  };

  if (
    previous.connected !==
    current.connected
  ) {
    push(
      "communication",
      "Communication API",
      previous.connected
        ? "CONNECTÉE"
        : "HORS LIGNE",
      current.connected
        ? "CONNECTÉE"
        : "HORS LIGNE",
    );
  }

  if (
    previous.deviceReady !==
    current.deviceReady
  ) {
    push(
      "device",
      "Readiness matériel",
      booleanLabel(
        previous.deviceReady,
        "PRÊT",
        "NON PRÊT",
      ),
      booleanLabel(
        current.deviceReady,
        "PRÊT",
        "NON PRÊT",
      ),
    );
  }

  if (
    previous.safetySafe !==
    current.safetySafe
  ) {
    push(
      "safety",
      "Chaîne de sécurité",
      booleanLabel(
        previous.safetySafe,
        "VALIDÉE",
        "BLOQUÉE",
      ),
      booleanLabel(
        current.safetySafe,
        "VALIDÉE",
        "BLOQUÉE",
      ),
    );
  }

  if (
    previous.pumpRunning !==
    current.pumpRunning
  ) {
    push(
      "pump",
      "Circulateur",
      previous.pumpRunning
        ? "EN MARCHE"
        : "À L’ARRÊT",
      current.pumpRunning
        ? "EN MARCHE"
        : "À L’ARRÊT",
    );
  }

  if (
    previous.valveOpen !==
    current.valveOpen
  ) {
    push(
      "valve",
      "Électrovanne",
      previous.valveOpen
        ? "OUVERTE"
        : "FERMÉE",
      current.valveOpen
        ? "OUVERTE"
        : "FERMÉE",
    );
  }

  if (
    previous.availableSensors !==
    current.availableSensors
  ) {
    push(
      "sensors",
      "Instrumentation thermique",
      `${previous.availableSensors}/4`,
      `${current.availableSensors}/4`,
    );
  }

  return events;
}

function latencyStatistics(
  samples: AvailabilitySample[],
): LatencyStatistics {
  const values =
    samples
      .map(
        (sample) =>
          sample.responseTime,
      )
      .filter(
        (value) =>
          Number.isFinite(value) &&
          value > 0,
      );

  if (values.length === 0) {
    return {
      count: 0,
      minimum: null,
      maximum: null,
      average: null,
    };
  }

  return {
    count:
      values.length,

    minimum:
      Math.min(...values),

    maximum:
      Math.max(...values),

    average:
      values.reduce(
        (total, value) =>
          total + value,
        0,
      ) / values.length,
  };
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

function formatDurationMs(
  milliseconds: number,
): string {
  const seconds =
    Math.max(
      0,
      Math.floor(
        milliseconds / 1_000,
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

  return `${days} j ${hours % 24} h`;
}

function escapeCsv(
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

function healthScore(
  checks: CheckNode[],
): number {
  if (checks.length === 0) {
    return 0;
  }

  const points = checks.reduce(
    (total, check) => {
      switch (check.tone) {
        case "good":
          return total + 100;

        case "warning":
          return total + 55;

        case "unknown":
          return total + 25;

        case "critical":
          return total;
      }
    },
    0,
  );

  return Math.round(
    points / checks.length,
  );
}

export default function HardwarePage() {
  const {
    snapshot,
    loading,
    refreshing,
    error,
    lastUpdate,
    responseTime,
    refresh,
  } = useGeoCooling();

  const [diagnosticEvents, setDiagnosticEvents] =
    useState<DiagnosticEvent[]>([]);

  const [availabilitySamples, setAvailabilitySamples] =
    useState<AvailabilitySample[]>([]);

  const [initialized, setInitialized] =
    useState(false);

  const [clock, setClock] =
    useState(Date.now());

  const previousStateRef =
    useRef<DiagnosticState | null>(
      null,
    );

  const connected =
    Boolean(snapshot && !error);

  const hydraulicCoherent =
    snapshot !== null &&
    snapshot.pumpRunning ===
      snapshot.valveOpen;

  const sensors: SensorNode[] = [
    {
      id: "source-in",
      label: "Arrivée forage",
      description:
        "Température source avant échange",
      value:
        snapshot?.sourceInTemperature,
    },
    {
      id: "source-out",
      label: "Retour forage",
      description:
        "Température source après échange",
      value:
        snapshot?.sourceOutTemperature,
    },
    {
      id: "supply",
      label: "Départ plancher",
      description:
        "Température envoyée au bâtiment",
      value:
        snapshot?.supplyTemperature,
    },
    {
      id: "return",
      label: "Retour plancher",
      description:
        "Température après échange bâtiment",
      value:
        snapshot?.returnTemperature,
    },
  ];

  const availableSensors =
    sensors.filter(
      (sensor) =>
        validNumber(sensor.value),
    ).length;

  const currentDiagnosticState =
    useMemo(
      () =>
        diagnosticStateFromValues(
          connected,
          snapshot,
          availableSensors,
        ),
      [
        connected,
        snapshot,
        availableSensors,
      ],
    );

  useEffect(() => {
    setDiagnosticEvents(
      readStoredArray<DiagnosticEvent>(
        DIAGNOSTIC_STORAGE_KEY,
      ).slice(
        -MAX_DIAGNOSTIC_EVENTS,
      ),
    );

    setAvailabilitySamples(
      readStoredArray<AvailabilitySample>(
        AVAILABILITY_STORAGE_KEY,
      ).slice(
        -MAX_AVAILABILITY_SAMPLES,
      ),
    );

    setInitialized(true);
  }, []);

  useEffect(() => {
    const timer =
      window.setInterval(
        () => {
          setClock(Date.now());
        },
        1_000,
      );

    return () => {
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    if (!initialized) {
      return;
    }

    const previous =
      previousStateRef.current;

    if (previous) {
      const created =
        buildDiagnosticEvents(
          previous,
          currentDiagnosticState,
        );

      if (created.length > 0) {
        setDiagnosticEvents(
          (current) => {
            const updated =
              [
                ...current,
                ...created,
              ].slice(
                -MAX_DIAGNOSTIC_EVENTS,
              );

            saveStoredArray(
              DIAGNOSTIC_STORAGE_KEY,
              updated,
            );

            return updated;
          },
        );
      }
    }

    previousStateRef.current =
      currentDiagnosticState;
  }, [
    initialized,
    currentDiagnosticState,
  ]);

  useEffect(() => {
    if (!initialized) {
      return;
    }

    const sample: AvailabilitySample = {
      timestamp:
        new Date().toISOString(),

      connected,

      responseTime,

      deviceReady:
        snapshot?.deviceReady ??
        null,
    };

    setAvailabilitySamples(
      (current) => {
        const previous =
          current.at(-1);

        if (
          previous &&
          new Date(
            sample.timestamp,
          ).getTime() -
            new Date(
              previous.timestamp,
            ).getTime() <
            9_000
        ) {
          return current;
        }

        const updated =
          [
            ...current,
            sample,
          ].slice(
            -MAX_AVAILABILITY_SAMPLES,
          );

        saveStoredArray(
          AVAILABILITY_STORAGE_KEY,
          updated,
        );

        return updated;
      },
    );
  }, [
    initialized,
    connected,
    responseTime,
    snapshot?.deviceReady,
    snapshot?.generatedAt,
  ]);

  const chain: ChainNode[] = [
    {
      id: "frontend",
      label: "Frontend Next.js",
      description:
        "Interface locale de supervision",
      value: "En ligne",
      tone: "good",
      source: "measured",
    },
    {
      id: "api",
      label: "API GeoCooling",
      description:
        "Lecture du snapshot normalisé",
      value: connected
        ? `${responseTime || 0} ms`
        : "Indisponible",
      tone: connected
        ? latencyTone(responseTime)
        : "critical",
      source: "measured",
    },
    {
      id: "backend",
      label: "Backend contrôleur",
      description:
        "Service applicatif GeoCooling",
      value: connected
        ? "Répond"
        : "Hors ligne",
      tone: connected
        ? "good"
        : "critical",
      source: "derived",
    },
    {
      id: "controller",
      label: "Contrôleur logique",
      description:
        "État global transmis par le snapshot",
      value:
        snapshot?.deviceReady === true
          ? "Prêt"
          : snapshot?.deviceReady === false
            ? "Non prêt"
            : "Non renseigné",
      tone: deviceTone(snapshot),
      source: "measured",
    },
    {
      id: "fieldbus",
      label: "Réseau terrain",
      description:
        "Modbus TCP / chemin matériel",
      value:
        snapshot?.deviceReady === true
          ? "Chaîne disponible"
          : snapshot?.deviceReady === false
            ? "Chaîne indisponible"
            : "Détail non exposé",
      tone: deviceTone(snapshot),
      source: "derived",
    },
    {
      id: "waveshare",
      label: "Waveshare 8 relais",
      description:
        "État individuel des relais",
      value:
        "Non exposé par le snapshot",
      tone: "unknown",
      source: "unavailable",
    },
    {
      id: "valve",
      label: "Électrovanne",
      description:
        "Sortie hydraulique vanne",
      value:
        snapshot?.valveOpen
          ? "Ouverte"
          : "Fermée",
      tone: outputTone(
        snapshot?.valveOpen,
        connected,
      ),
      source: "measured",
    },
    {
      id: "pump",
      label: "Circulateur",
      description:
        "Sortie hydraulique pompe",
      value:
        snapshot?.pumpRunning
          ? "En marche"
          : "À l’arrêt",
      tone: outputTone(
        snapshot?.pumpRunning,
        connected,
      ),
      source: "measured",
    },
  ];

  const checks: CheckNode[] = [
    {
      id: "communication",
      label: "Communication applicative",
      detail: connected
        ? "Snapshot reçu correctement"
        : error ||
          "Aucun snapshot disponible",
      tone: connected
        ? latencyTone(responseTime)
        : "critical",
    },
    {
      id: "controller-ready",
      label: "Contrôleur prêt",
      detail:
        snapshot?.deviceReady === true
          ? "Driver matériel déclaré prêt"
          : snapshot?.deviceReady === false
            ? "Driver matériel non prêt"
            : "État non transmis",
      tone: deviceTone(snapshot),
    },
    {
      id: "safety",
      label: "Chaîne de sécurité",
      detail:
        snapshot?.safetySafe === true
          ? "Conditions validées"
          : snapshot?.safetySafe === false
            ? "Blocage sécurité actif"
            : "État non transmis",
      tone: safetyTone(snapshot),
    },
    {
      id: "hydraulic",
      label: "Cohérence hydraulique",
      detail: hydraulicCoherent
        ? "Pompe et vanne cohérentes"
        : "États pompe / vanne différents",
      tone:
        snapshot === null
          ? "unknown"
          : hydraulicCoherent
            ? "good"
            : "warning",
    },
    {
      id: "sensors",
      label: "Instrumentation thermique",
      detail:
        `${availableSensors}/4 sondes disponibles`,
      tone:
        availableSensors === 4
          ? "good"
          : availableSensors > 0
            ? "warning"
            : "critical",
    },
    {
      id: "relay-detail",
      label: "Détail des huit relais",
      detail:
        "Non transmis par l’API snapshot actuelle",
      tone: "unknown",
    },
  ];

  const score =
    healthScore(checks);

  const globalTone: HealthTone =
    checks.some(
      (check) =>
        check.tone === "critical",
    )
      ? "critical"
      : checks.some(
            (check) =>
              check.tone === "warning",
          )
        ? "warning"
        : connected
          ? "good"
          : "unknown";

  const floorDelta =
    validNumber(
      snapshot?.returnTemperature,
    ) &&
    validNumber(
      snapshot?.supplyTemperature,
    )
      ? snapshot.returnTemperature -
        snapshot.supplyTemperature
      : null;

  const sourceDelta =
    validNumber(
      snapshot?.sourceOutTemperature,
    ) &&
    validNumber(
      snapshot?.sourceInTemperature,
    )
      ? snapshot.sourceOutTemperature -
        snapshot.sourceInTemperature
      : null;

  const latency =
    useMemo(
      () =>
        latencyStatistics(
          availabilitySamples,
        ),
      [availabilitySamples],
    );

  const connectedSamples =
    availabilitySamples.filter(
      (sample) =>
        sample.connected,
    ).length;

  const readySamples =
    availabilitySamples.filter(
      (sample) =>
        sample.deviceReady === true,
    ).length;

  const communicationAvailability =
    availabilitySamples.length === 0
      ? null
      : Math.round(
          (
            connectedSamples /
            availabilitySamples.length
          ) *
            100,
        );

  const hardwareAvailability =
    availabilitySamples.length === 0
      ? null
      : Math.round(
          (
            readySamples /
            availabilitySamples.length
          ) *
            100,
        );

  const communicationLosses =
    diagnosticEvents.filter(
      (event) =>
        event.type ===
          "communication" &&
        event.currentValue ===
          "HORS LIGNE",
    ).length;

  const pumpTransitions =
    diagnosticEvents.filter(
      (event) =>
        event.type === "pump",
    ).length;

  const valveTransitions =
    diagnosticEvents.filter(
      (event) =>
        event.type === "valve",
    ).length;

  const safetyTransitions =
    diagnosticEvents.filter(
      (event) =>
        event.type === "safety",
    ).length;

  const latestEvent =
    diagnosticEvents.at(-1) ??
    null;

  const currentStateSince =
    latestEvent?.occurredAt ??
    availabilitySamples[0]
      ?.timestamp ??
    snapshot?.generatedAt ??
    null;

  const stateDuration =
    currentStateSince
      ? clock -
        new Date(
          currentStateSince,
        ).getTime()
      : 0;

  const clearDiagnostics = () => {
    setDiagnosticEvents([]);
    setAvailabilitySamples([]);

    try {
      window.localStorage.removeItem(
        DIAGNOSTIC_STORAGE_KEY,
      );

      window.localStorage.removeItem(
        AVAILABILITY_STORAGE_KEY,
      );
    } catch {
      // Stockage local indisponible.
    }
  };

  const exportDiagnosticJson = () => {
    const payload = {
      exportedAt:
        new Date().toISOString(),

      currentState:
        currentDiagnosticState,

      healthScore:
        score,

      availability: {
        communicationPercent:
          communicationAvailability,

        hardwarePercent:
          hardwareAvailability,

        sampleCount:
          availabilitySamples.length,

        communicationLosses,

        latency,
      },

      transitions: {
        pump:
          pumpTransitions,

        valve:
          valveTransitions,

        safety:
          safetyTransitions,
      },

      diagnosticEvents,

      availabilitySamples,
    };

    downloadTextFile(
      JSON.stringify(
        payload,
        null,
        2,
      ),
      `geocooling-hardware-diagnostic-${new Date()
        .toISOString()
        .replaceAll(
          ":",
          "-",
        )}.json`,
      "application/json;charset=utf-8",
    );
  };

  const exportDiagnosticCsv = () => {
    if (
      diagnosticEvents.length === 0
    ) {
      return;
    }

    const header = [
      "event_id",
      "occurred_at",
      "type",
      "label",
      "previous_value",
      "current_value",
      "severity",
    ];

    const rows =
      diagnosticEvents.map(
        (event) => [
          event.id,
          event.occurredAt,
          event.type,
          event.label,
          event.previousValue,
          event.currentValue,
          event.severity,
        ],
      );

    const csv =
      [
        header,
        ...rows,
      ]
        .map(
          (row) =>
            row
              .map(escapeCsv)
              .join(";"),
        )
        .join("\n");

    downloadTextFile(
      csv,
      `geocooling-hardware-events-${new Date()
        .toISOString()
        .replaceAll(
          ":",
          "-",
        )}.csv`,
      "text/csv;charset=utf-8",
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
            HARDWARE CHAIN ENTERPRISE
          </p>

          <h2>
            Chaîne matérielle GeoCooling
          </h2>

          <p>
            Supervision du chemin complet entre
            l’interface, le backend, le contrôleur,
            les actionneurs et l’instrumentation.
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
            label={toneLabel(globalTone)}
            tone={
              globalTone === "good"
                ? "success"
                : globalTone === "warning"
                  ? "warning"
                  : globalTone === "critical"
                    ? "danger"
                    : "neutral"
            }
            pulse={
              globalTone === "good"
            }
          />
        </div>
      </section>

      {loading && !snapshot ? (
        <section className="gc-loading-state">
          <div className="gc-loading-spinner" />

          <div>
            <strong>
              Analyse de la chaîne matérielle…
            </strong>

            <span>
              Lecture du premier snapshot.
            </span>
          </div>
        </section>
      ) : null}

      <section className="gc-hw-chain-overview">
        <article
          className={`gc-hw-chain-global ${toneClass(
            globalTone,
          )}`}
        >
          <div className="gc-hw-chain-global__indicator">
            <span />
          </div>

          <div>
            <span className="gc-hw-chain-label">
              ÉTAT GLOBAL
            </span>

            <strong>
              {globalTone === "good"
                ? "La chaîne exposée par le snapshot est opérationnelle."
                : globalTone === "warning"
                  ? "La chaîne fonctionne avec au moins une condition dégradée."
                  : globalTone === "critical"
                    ? "Une condition critique empêche la validation complète."
                    : "Les données disponibles ne permettent pas une validation complète."}
            </strong>
          </div>
        </article>

        <article className="gc-hw-chain-score">
          <header>
            <div>
              <span className="gc-hw-chain-label">
                SCORE DE SANTÉ
              </span>

              <strong>
                {checks.filter(
                  (check) =>
                    check.tone === "good",
                ).length}
                /{checks.length} contrôles validés
              </strong>
            </div>

            <div>
              <strong>{score}</strong>
              <span>%</span>
            </div>
          </header>

          <div>
            <span
              className={
                score >= 85
                  ? "is-good"
                  : score >= 55
                    ? "is-warning"
                    : "is-critical"
              }
              style={{
                width: `${score}%`,
              }}
            />
          </div>
        </article>
      </section>

      <section className="gc-hw-chain-kpis">
        <article>
          <span>LATENCE API</span>

          <strong
            className={toneClass(
              latencyTone(responseTime),
            )}
          >
            {responseTime > 0
              ? `${responseTime} ms`
              : "—"}
          </strong>

          <small>
            Temps de réponse frontend
          </small>
        </article>

        <article>
          <span>SONDES DISPONIBLES</span>

          <strong
            className={
              availableSensors === 4
                ? "is-good"
                : "is-warning"
            }
          >
            {availableSensors}/4
          </strong>

          <small>
            Mesures hydrauliques
          </small>
        </article>

        <article>
          <span>ΔT SOURCE</span>

          <strong>
            {sourceDelta === null
              ? "—"
              : `${sourceDelta.toFixed(
                  1,
                )} °C`}
          </strong>

          <small>
            Sortie moins entrée
          </small>
        </article>

        <article>
          <span>ΔT PLANCHER</span>

          <strong>
            {floorDelta === null
              ? "—"
              : `${floorDelta.toFixed(
                  1,
                )} °C`}
          </strong>

          <small>
            Retour moins départ
          </small>
        </article>

        <article>
          <span>SÉCURITÉ</span>

          <strong
            className={toneClass(
              safetyTone(snapshot),
            )}
          >
            {snapshot?.safetySafe === true
              ? "VALIDÉE"
              : snapshot?.safetySafe === false
                ? "BLOQUÉE"
                : "INCONNUE"}
          </strong>

          <small>
            État transmis
          </small>
        </article>
      </section>

      <section className="gc-hw-chain-panel">
        <header>
          <div>
            <p className="gc-page-header__eyebrow">
              CHEMIN DE COMMUNICATION
            </p>

            <h3>
              Infrastructure de bout en bout
            </h3>
          </div>

          <span>
            Mesuré, déduit ou non exposé
          </span>
        </header>

        <div className="gc-hw-chain-map">
          {chain.map(
            (node, index) => (
              <div
                key={node.id}
                className="gc-hw-chain-map__item"
              >
                <article
                  className={toneClass(
                    node.tone,
                  )}
                >
                  <header>
                    <div>
                      <span
                        className="gc-hw-chain-map__led"
                        aria-hidden="true"
                      />

                      <strong>
                        {node.label}
                      </strong>
                    </div>

                    <b>
                      {sourceLabel(
                        node.source,
                      )}
                    </b>
                  </header>

                  <p>
                    {node.description}
                  </p>

                  <footer>
                    <strong>
                      {node.value}
                    </strong>

                    <span>
                      {toneLabel(
                        node.tone,
                      )}
                    </span>
                  </footer>
                </article>

                {index <
                chain.length - 1 ? (
                  <div
                    className={`gc-hw-chain-link ${
                      node.tone ===
                        "critical" ||
                      chain[index + 1]
                        .tone ===
                        "critical"
                        ? "is-critical"
                        : node.tone ===
                              "unknown" ||
                            chain[index + 1]
                              .tone ===
                              "unknown"
                          ? "is-unknown"
                          : "is-good"
                    }`}
                    aria-hidden="true"
                  >
                    <span />
                    <span />
                    <span />
                  </div>
                ) : null}
              </div>
            ),
          )}
        </div>
      </section>

      <section className="gc-hw-chain-layout">
        <article className="gc-hw-action-panel">
          <header>
            <div>
              <p className="gc-page-header__eyebrow">
                ACTIONNEURS
              </p>

              <h3>
                Sorties hydrauliques
              </h3>
            </div>

            <strong
              className={
                hydraulicCoherent
                  ? "is-good"
                  : "is-warning"
              }
            >
              {hydraulicCoherent
                ? "COHÉRENT"
                : "TRANSITION"}
            </strong>
          </header>

          <div>
            <article
              className={
                snapshot?.valveOpen
                  ? "is-active"
                  : "is-idle"
              }
            >
              <div className="gc-hw-action-icon">
                <span>V</span>
              </div>

              <section>
                <span>
                  ÉLECTROVANNE
                </span>

                <strong>
                  {snapshot?.valveOpen
                    ? "OUVERTE"
                    : "FERMÉE"}
                </strong>

                <small>
                  État transmis par le snapshot
                </small>
              </section>

              <i />
            </article>

            <article
              className={
                snapshot?.pumpRunning
                  ? "is-active"
                  : "is-idle"
              }
            >
              <div className="gc-hw-action-icon">
                <span
                  className={
                    snapshot?.pumpRunning
                      ? "is-spinning"
                      : ""
                  }
                >
                  ↻
                </span>
              </div>

              <section>
                <span>
                  CIRCULATEUR
                </span>

                <strong>
                  {snapshot?.pumpRunning
                    ? "EN MARCHE"
                    : "À L’ARRÊT"}
                </strong>

                <small>
                  État transmis par le snapshot
                </small>
              </section>

              <i />
            </article>
          </div>

          <aside>
            <span>LIMITATION API</span>

            <p>
              Le snapshot ne fournit pas encore
              l’adresse, le numéro de canal, le retour
              de lecture ou l’état individuel des huit
              relais Waveshare.
            </p>
          </aside>
        </article>

        <article className="gc-hw-sensor-panel">
          <header>
            <div>
              <p className="gc-page-header__eyebrow">
                INSTRUMENTATION
              </p>

              <h3>
                Sondes thermiques
              </h3>
            </div>

            <strong>
              {availableSensors}/4
            </strong>
          </header>

          <div>
            {sensors.map(
              (sensor, index) => {
                const online =
                  validNumber(
                    sensor.value,
                  );

                return (
                  <article
                    key={sensor.id}
                    className={
                      online
                        ? "is-online"
                        : "is-offline"
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
                        {sensor.label}
                      </strong>

                      <small>
                        {
                          sensor.description
                        }
                      </small>
                    </div>

                    <b>
                      {temperature(
                        sensor.value,
                      )}
                    </b>

                    <i />
                  </article>
                );
              },
            )}
          </div>
        </article>
      </section>

      <section className="gc-hw-diagnostic-panel">
        <header>
          <div>
            <p className="gc-page-header__eyebrow">
              DIAGNOSTIC DE DISPONIBILITÉ
            </p>

            <h3>
              Continuité de service
            </h3>
          </div>

          <div className="gc-hw-diagnostic-actions">
            <button
              type="button"
              onClick={exportDiagnosticCsv}
              disabled={
                diagnosticEvents.length === 0
              }
            >
              Export CSV
            </button>

            <button
              type="button"
              onClick={exportDiagnosticJson}
            >
              Export JSON
            </button>

            <button
              type="button"
              className="is-danger"
              onClick={clearDiagnostics}
              disabled={
                diagnosticEvents.length === 0 &&
                availabilitySamples.length === 0
              }
            >
              Réinitialiser
            </button>
          </div>
        </header>

        <div className="gc-hw-diagnostic-kpis">
          <article>
            <span>
              DISPONIBILITÉ API
            </span>

            <strong
              className={
                communicationAvailability === null
                  ? "is-unknown"
                  : communicationAvailability >= 99
                    ? "is-good"
                    : communicationAvailability >= 90
                      ? "is-warning"
                      : "is-critical"
              }
            >
              {communicationAvailability === null
                ? "—"
                : `${communicationAvailability} %`}
            </strong>

            <small>
              {availabilitySamples.length} échantillon(s)
            </small>
          </article>

          <article>
            <span>
              DISPONIBILITÉ MATÉRIEL
            </span>

            <strong
              className={
                hardwareAvailability === null
                  ? "is-unknown"
                  : hardwareAvailability >= 99
                    ? "is-good"
                    : hardwareAvailability >= 90
                      ? "is-warning"
                      : "is-critical"
              }
            >
              {hardwareAvailability === null
                ? "—"
                : `${hardwareAvailability} %`}
            </strong>

            <small>
              Driver déclaré prêt
            </small>
          </article>

          <article>
            <span>
              PERTES DE COMMUNICATION
            </span>

            <strong
              className={
                communicationLosses === 0
                  ? "is-good"
                  : "is-critical"
              }
            >
              {communicationLosses}
            </strong>

            <small>
              Transitions vers hors ligne
            </small>
          </article>

          <article>
            <span>
              LATENCE MOYENNE
            </span>

            <strong>
              {latency.average === null
                ? "—"
                : `${Math.round(
                    latency.average,
                  )} ms`}
            </strong>

            <small>
              Min.{" "}
              {latency.minimum === null
                ? "—"
                : `${latency.minimum} ms`}
              {" · Max. "}
              {latency.maximum === null
                ? "—"
                : `${latency.maximum} ms`}
            </small>
          </article>

          <article>
            <span>
              ÉTAT ACTUEL DEPUIS
            </span>

            <strong>
              {formatDurationMs(
                Math.max(
                  0,
                  stateDuration,
                ),
              )}
            </strong>

            <small>
              {formatDateTime(
                currentStateSince,
              )}
            </small>
          </article>
        </div>

        <div className="gc-hw-diagnostic-layout">
          <article className="gc-hw-transition-panel">
            <header>
              <div>
                <span>
                  COMPTEURS DE TRANSITIONS
                </span>

                <strong>
                  Activité de la session
                </strong>
              </div>
            </header>

            <div>
              <article>
                <span>POMPE</span>
                <strong>
                  {pumpTransitions}
                </strong>
                <small>
                  Changements d’état
                </small>
              </article>

              <article>
                <span>VANNE</span>
                <strong>
                  {valveTransitions}
                </strong>
                <small>
                  Changements d’état
                </small>
              </article>

              <article>
                <span>SÉCURITÉ</span>
                <strong>
                  {safetyTransitions}
                </strong>
                <small>
                  Changements d’état
                </small>
              </article>

              <article>
                <span>TOTAL</span>
                <strong>
                  {diagnosticEvents.length}
                </strong>
                <small>
                  Événements conservés
                </small>
              </article>
            </div>
          </article>

          <article className="gc-hw-latency-panel">
            <header>
              <div>
                <span>
                  DISPONIBILITÉ TEMPORELLE
                </span>

                <strong>
                  Derniers échantillons
                </strong>
              </div>

              <b>
                {availabilitySamples.length}
              </b>
            </header>

            <div className="gc-hw-availability-strip">
              {availabilitySamples
                .slice(-120)
                .map(
                  (sample) => (
                    <span
                      key={sample.timestamp}
                      className={
                        !sample.connected
                          ? "is-critical"
                          : sample.deviceReady === false
                            ? "is-warning"
                            : sample.deviceReady === true
                              ? "is-good"
                              : "is-unknown"
                      }
                      title={`${formatDateTime(
                        sample.timestamp,
                      )} — ${
                        sample.connected
                          ? "API connectée"
                          : "API hors ligne"
                      } — ${sample.responseTime} ms`}
                    />
                  ),
                )}
            </div>

            <footer>
              <span>
                <i className="is-good" />
                Disponible
              </span>

              <span>
                <i className="is-warning" />
                Non prêt
              </span>

              <span>
                <i className="is-critical" />
                Hors ligne
              </span>

              <span>
                <i className="is-unknown" />
                Inconnu
              </span>
            </footer>
          </article>
        </div>

        <article className="gc-hw-event-journal">
          <header>
            <div>
              <span>
                JOURNAL DES CHANGEMENTS
              </span>

              <strong>
                50 derniers événements
              </strong>
            </div>

            <b>
              {diagnosticEvents.length}
            </b>
          </header>

          {diagnosticEvents.length === 0 ? (
            <div className="gc-hw-event-empty">
              <span>✓</span>

              <div>
                <strong>
                  Aucun changement enregistré
                </strong>

                <small>
                  Le journal sera alimenté lors des
                  prochaines transitions matérielles.
                </small>
              </div>
            </div>
          ) : (
            <div className="gc-hw-event-list">
              {[...diagnosticEvents]
                .slice(-50)
                .reverse()
                .map(
                  (event) => (
                    <article
                      key={event.id}
                      className={toneClass(
                        event.severity,
                      )}
                    >
                      <span>
                        {event.severity === "good"
                          ? "✓"
                          : event.severity === "unknown"
                            ? "?"
                            : "!"}
                      </span>

                      <div>
                        <strong>
                          {event.label}
                        </strong>

                        <small>
                          {event.previousValue}
                          {" → "}
                          {event.currentValue}
                        </small>
                      </div>

                      <section>
                        <strong>
                          {formatDateTime(
                            event.occurredAt,
                          )}
                        </strong>

                        <small>
                          {event.type}
                        </small>
                      </section>
                    </article>
                  ),
                )}
            </div>
          )}
        </article>
      </section>

      <section className="gc-hw-check-panel">
        <header>
          <div>
            <p className="gc-page-header__eyebrow">
              CERTIFICATION OPÉRATIONNELLE
            </p>

            <h3>
              Contrôles de disponibilité
            </h3>
          </div>

          <strong>
            {score} %
          </strong>
        </header>

        <div>
          {checks.map(
            (check) => (
              <article
                key={check.id}
                className={toneClass(
                  check.tone,
                )}
              >
                <span>
                  {check.tone === "good"
                    ? "✓"
                    : check.tone === "unknown"
                      ? "?"
                      : "!"}
                </span>

                <div>
                  <strong>
                    {check.label}
                  </strong>

                  <small>
                    {check.detail}
                  </small>
                </div>

                <b>
                  {toneLabel(
                    check.tone,
                  )}
                </b>
              </article>
            ),
          )}
        </div>
      </section>
    </AppShell>
  );
}
