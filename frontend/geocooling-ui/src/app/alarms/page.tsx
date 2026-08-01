"use client";

import Link from "next/link";
import type { GeoCoolingSnapshot } from "@/types/geocooling";
import { AppShell } from "@/components/layout/AppShell";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useGeoCooling } from "@/hooks/useGeoCooling";

type AlarmSeverity = "critical" | "warning" | "information";

type AlarmItem = {
  id: string;
  title: string;
  description: string;
  severity: AlarmSeverity;
  active: boolean;
  source: string;
  recommendation: string;
};

function validNumber(
  value: number | null | undefined,
): value is number {
  return typeof value === "number" && Number.isFinite(value);
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
    (a * temperature) / (b + temperature);

  return (b * gamma) / (a - gamma);
}

function buildAlarms(
  snapshot: GeoCoolingSnapshot | null,
  connected: boolean,
  error: string | null,
): AlarmItem[] {
  const calculatedDewPoint = dewPoint(
    snapshot?.indoorTemperature,
    snapshot?.humidity,
  );

  const condensationMargin =
    calculatedDewPoint !== null &&
    validNumber(snapshot?.supplyTemperature)
      ? snapshot.supplyTemperature - calculatedDewPoint
      : null;

  const hydraulicMismatch =
    snapshot !== null &&
    snapshot.pumpRunning !== snapshot.valveOpen;

  const missingSensors = [
    snapshot?.sourceInTemperature,
    snapshot?.sourceOutTemperature,
    snapshot?.supplyTemperature,
    snapshot?.returnTemperature,
  ].filter((value) => !validNumber(value)).length;

  return [
    {
      id: "backend-offline",
      title: "Communication backend interrompue",
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
      title: "Sécurité générale bloquante",
      description:
        "Le contrôleur indique que les conditions de sécurité ne sont pas validées.",
      severity: "critical",
      active: snapshot?.safetySafe === false,
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
      active: snapshot?.deviceReady === false,
      source: "Driver matériel",
      recommendation:
        "Contrôler l’alimentation, le Waveshare, Modbus TCP et les relais configurés.",
    },
    {
      id: "hydraulic-mismatch",
      title: "Séquence hydraulique incohérente",
      description:
        "La pompe et l’électrovanne ne sont pas dans le même état.",
      severity: "warning",
      active: hydraulicMismatch,
      source: "Hydraulique",
      recommendation:
        "Vérifier la séquence de commande et les retours d’état des équipements.",
    },
    {
      id: "condensation-risk",
      title: "Risque de condensation",
      description:
        condensationMargin === null
          ? "La marge de condensation ne peut pas être calculée."
          : `La marge calculée est de ${condensationMargin.toFixed(1)} °C.`,
      severity:
        condensationMargin !== null && condensationMargin < 2
          ? "critical"
          : "warning",
      active:
        condensationMargin !== null &&
        condensationMargin < 3,
      source: "Thermique",
      recommendation:
        "Augmenter la température de départ ou suspendre le rafraîchissement.",
    },
    {
      id: "sensors-missing",
      title: "Télémétrie hydraulique incomplète",
      description:
        `${missingSensors} sonde(s) hydraulique(s) ne transmettent pas de valeur exploitable.`,
      severity: "warning",
      active: missingSensors > 0,
      source: "Instrumentation",
      recommendation:
        "Contrôler les DS18B20, le bus 1-Wire et la remontée du snapshot.",
    },
    {
      id: "manual-mode",
      title: "Mode manuel actif",
      description:
        "Le système n’est pas piloté en mode automatique.",
      severity: "information",
      active: snapshot?.mode === "manual",
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
      active: snapshot?.mode === "simulation",
      source: "Stratégie",
      recommendation:
        "Ne pas considérer les états simulés comme une validation matérielle.",
    },
  ];
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

  const connected = Boolean(snapshot && !error);

  const alarms = buildAlarms(
    snapshot,
    connected,
    error,
  );

  const activeAlarms = alarms.filter(
    (alarm) => alarm.active,
  );

  const criticalCount = activeAlarms.filter(
    (alarm) => alarm.severity === "critical",
  ).length;

  const warningCount = activeAlarms.filter(
    (alarm) => alarm.severity === "warning",
  ).length;

  const informationCount = activeAlarms.filter(
    (alarm) => alarm.severity === "information",
  ).length;

  return (
    <AppShell
      connected={connected}
      mode={String(snapshot?.mode ?? "INCONNU")}
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
            SUPERVISION DES ÉVÉNEMENTS
          </p>

          <h2>Alarmes & diagnostics</h2>

          <p>
            Détection locale des anomalies de communication,
            sécurité, hydraulique et télémétrie.
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
              activeAlarms.length === 0
                ? "AUCUNE ALARME"
                : `${activeAlarms.length} ACTIVE(S)`
            }
            tone={
              criticalCount > 0
                ? "danger"
                : warningCount > 0
                  ? "warning"
                  : activeAlarms.length > 0
                    ? "info"
                    : "success"
            }
            pulse={criticalCount > 0}
          />
        </div>
      </section>

      <section className="gc-alarm-kpis">
        <article className="is-critical">
          <span>CRITIQUES</span>
          <strong>{criticalCount}</strong>
          <small>Intervention immédiate</small>
        </article>

        <article className="is-warning">
          <span>AVERTISSEMENTS</span>
          <strong>{warningCount}</strong>
          <small>Surveillance nécessaire</small>
        </article>

        <article className="is-information">
          <span>INFORMATIONS</span>
          <strong>{informationCount}</strong>
          <small>État ou mode particulier</small>
        </article>

        <article
          className={
            connected ? "is-good" : "is-critical"
          }
        >
          <span>SUPERVISION</span>
          <strong>
            {connected ? "ON" : "OFF"}
          </strong>
          <small>
            {loading
              ? "Connexion en cours"
              : connected
                ? "Snapshot disponible"
                : "Données indisponibles"}
          </small>
        </article>
      </section>

      {activeAlarms.length === 0 ? (
        <section className="gc-alarm-empty">
          <div aria-hidden="true">✓</div>

          <strong>
            Aucun événement actif
          </strong>

          <p>
            Les contrôles de communication, sécurité,
            hydraulique et instrumentation ne détectent
            actuellement aucune anomalie.
          </p>
        </section>
      ) : (
        <section className="gc-alarm-list">
          {activeAlarms.map((alarm) => (
            <article
              key={alarm.id}
              className={`gc-alarm-item is-${alarm.severity}`}
            >
              <div className="gc-alarm-item__severity">
                <span />
              </div>

              <div className="gc-alarm-item__content">
                <header>
                  <div>
                    <span className="gc-alarm-item__source">
                      {alarm.source}
                    </span>

                    <h3>{alarm.title}</h3>
                  </div>

                  <StatusBadge
                    label={severityLabel(alarm.severity)}
                    tone={severityTone(alarm.severity)}
                    pulse={alarm.severity === "critical"}
                  />
                </header>

                <p>
                  {alarm.description}
                </p>

                <div className="gc-alarm-item__recommendation">
                  <span>RECOMMANDATION</span>
                  <strong>
                    {alarm.recommendation}
                  </strong>
                </div>
              </div>
            </article>
          ))}
        </section>
      )}

      <section className="gc-alarm-checks">
        <header>
          <div>
            <p className="gc-page-header__eyebrow">
              CONTRÔLES AUTOMATIQUES
            </p>

            <h2>
              Matrice de surveillance
            </h2>
          </div>

          <span>
            {alarms.length} règles évaluées
          </span>
        </header>

        <div>
          {alarms.map((alarm) => (
            <article
              key={`check-${alarm.id}`}
              className={
                alarm.active
                  ? `is-${alarm.severity}`
                  : "is-clear"
              }
            >
              <span>
                {alarm.active ? "!" : "✓"}
              </span>

              <div>
                <strong>{alarm.title}</strong>
                <small>
                  {alarm.active
                    ? severityLabel(alarm.severity)
                    : "CONTRÔLE VALIDÉ"}
                </small>
              </div>
            </article>
          ))}
        </div>
      </section>
    </AppShell>
  );
}
