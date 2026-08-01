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
