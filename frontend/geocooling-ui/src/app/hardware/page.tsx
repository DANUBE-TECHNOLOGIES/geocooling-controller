"use client";

import Link from "next/link";
import type { GeoCoolingSnapshot } from "@/types/geocooling";
import { AppShell } from "@/components/layout/AppShell";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useGeoCooling } from "@/hooks/useGeoCooling";

type HardwareState = {
  label: string;
  tone: "success" | "warning" | "danger" | "neutral";
  className: string;
  description: string;
};

type HardwareCheck = {
  id: string;
  label: string;
  detail: string;
  valid: boolean;
  warning?: boolean;
};

function validNumber(
  value: number | null | undefined,
): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function hardwareState(
  snapshot: GeoCoolingSnapshot | null,
  connected: boolean,
): HardwareState {
  if (!connected || !snapshot) {
    return {
      label: "HORS LIGNE",
      tone: "danger",
      className: "is-critical",
      description:
        "Aucune télémétrie matérielle n’est disponible.",
    };
  }

  if (snapshot.safetySafe === false) {
    return {
      label: "BLOQUÉ",
      tone: "danger",
      className: "is-critical",
      description:
        "Le contrôleur signale une condition de sécurité bloquante.",
    };
  }

  if (snapshot.deviceReady === false) {
    return {
      label: "NON PRÊT",
      tone: "warning",
      className: "is-warning",
      description:
        "Le backend répond mais le matériel n’est pas déclaré prêt.",
    };
  }

  if (
    snapshot.pumpRunning !==
    snapshot.valveOpen
  ) {
    return {
      label: "TRANSITION",
      tone: "warning",
      className: "is-warning",
      description:
        "Les deux sorties hydrauliques ne sont pas dans le même état.",
    };
  }

  return {
    label: "OPÉRATIONNEL",
    tone: "success",
    className: "is-good",
    description:
      "Le contrôleur et la chaîne matérielle sont disponibles.",
  };
}

function formatTemperature(
  value: number | null | undefined,
): string {
  return validNumber(value)
    ? `${value.toFixed(1)} °C`
    : "Non disponible";
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

  const connected = Boolean(snapshot && !error);

  const state = hardwareState(
    snapshot,
    connected,
  );

  const hydraulicCoherent =
    snapshot !== null &&
    snapshot.pumpRunning ===
      snapshot.valveOpen;

  const sensorValues = [
    snapshot?.sourceInTemperature,
    snapshot?.sourceOutTemperature,
    snapshot?.supplyTemperature,
    snapshot?.returnTemperature,
  ];

  const availableSensors =
    sensorValues.filter(validNumber).length;

  const checks: HardwareCheck[] = [
    {
      id: "backend",
      label: "Communication backend",
      detail: connected
        ? "Snapshot reçu correctement"
        : "Aucune communication",
      valid: connected,
    },
    {
      id: "device",
      label: "Disponibilité du matériel",
      detail:
        snapshot?.deviceReady === true
          ? "Driver matériel prêt"
          : snapshot?.deviceReady === false
            ? "Driver matériel non prêt"
            : "État non transmis",
      valid:
        snapshot?.deviceReady === true,
      warning:
        snapshot?.deviceReady === null ||
        snapshot?.deviceReady === undefined,
    },
    {
      id: "safety",
      label: "Chaîne de sécurité",
      detail:
        snapshot?.safetySafe === true
          ? "Conditions validées"
          : snapshot?.safetySafe === false
            ? "Blocage actif"
            : "État non transmis",
      valid:
        snapshot?.safetySafe === true,
      warning:
        snapshot?.safetySafe === null ||
        snapshot?.safetySafe === undefined,
    },
    {
      id: "outputs",
      label: "Cohérence des sorties",
      detail: hydraulicCoherent
        ? "Pompe et vanne cohérentes"
        : "Séquence intermédiaire",
      valid: hydraulicCoherent,
      warning: !hydraulicCoherent,
    },
    {
      id: "sensors",
      label: "Instrumentation thermique",
      detail:
        `${availableSensors}/4 sondes hydrauliques disponibles`,
      valid: availableSensors === 4,
      warning:
        availableSensors > 0 &&
        availableSensors < 4,
    },
  ];

  const validChecks =
    checks.filter(
      (check) => check.valid,
    ).length;

  const readinessScore =
    Math.round(
      (validChecks / checks.length) *
        100,
    );

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
            SUPERVISION TERRAIN
          </p>

          <h2>Matériel & instrumentation</h2>

          <p>
            Vue opérationnelle des sorties,
            capteurs, sécurités et de la
            disponibilité matérielle du système.
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
            label={state.label}
            tone={state.tone}
            pulse={
              state.tone === "success"
            }
          />
        </div>
      </section>

      {loading && !snapshot ? (
        <section className="gc-loading-state">
          <div className="gc-loading-spinner" />

          <div>
            <strong>
              Lecture de l’état matériel…
            </strong>

            <span>
              Connexion au contrôleur.
            </span>
          </div>
        </section>
      ) : null}

      <section className="gc-hardware-overview">
        <article
          className={`gc-hardware-state ${state.className}`}
        >
          <div className="gc-hardware-state__indicator">
            <span />
          </div>

          <div>
            <span className="gc-hardware-label">
              ÉTAT GLOBAL
            </span>

            <strong>
              {state.description}
            </strong>
          </div>
        </article>

        <article className="gc-hardware-readiness">
          <header>
            <div>
              <span className="gc-hardware-label">
                READINESS MATÉRIEL
              </span>

              <strong>
                {validChecks}/{checks.length} contrôles
              </strong>
            </div>

            <div>
              <strong>
                {readinessScore}
              </strong>

              <span>%</span>
            </div>
          </header>

          <div className="gc-hardware-progress">
            <div
              className={
                readinessScore === 100
                  ? "is-good"
                  : readinessScore >= 60
                    ? "is-warning"
                    : "is-critical"
              }
              style={{
                width: `${readinessScore}%`,
              }}
            />
          </div>
        </article>
      </section>

      <section className="gc-hardware-grid">
        <article className="gc-hardware-panel">
          <header>
            <div>
              <span className="gc-hardware-label">
                SORTIES DE COMMANDE
              </span>

              <h3>Actionneurs hydrauliques</h3>
            </div>

            <strong>
              {hydraulicCoherent
                ? "COHÉRENT"
                : "TRANSITION"}
            </strong>
          </header>

          <div className="gc-hardware-output-grid">
            <article
              className={
                snapshot?.valveOpen
                  ? "is-active"
                  : "is-idle"
              }
            >
              <div className="gc-hardware-output__icon">
                <span>V</span>
              </div>

              <div>
                <span className="gc-hardware-label">
                  ÉLECTROVANNE
                </span>

                <strong>
                  {snapshot?.valveOpen
                    ? "OUVERTE"
                    : "FERMÉE"}
                </strong>

                <small>
                  Sortie de commande vanne
                </small>
              </div>

              <i />
            </article>

            <article
              className={
                snapshot?.pumpRunning
                  ? "is-active"
                  : "is-idle"
              }
            >
              <div className="gc-hardware-output__icon">
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

              <div>
                <span className="gc-hardware-label">
                  CIRCULATEUR
                </span>

                <strong>
                  {snapshot?.pumpRunning
                    ? "EN MARCHE"
                    : "ARRÊTÉ"}
                </strong>

                <small>
                  Sortie de commande pompe
                </small>
              </div>

              <i />
            </article>
          </div>

          <div className="gc-hardware-note">
            <span>INFORMATION</span>

            <p>
              Cette page affiche les états
              confirmés par le snapshot. Le
              détail physique des huit relais
              Modbus n’est pas encore exposé
              individuellement par l’API frontend.
            </p>
          </div>
        </article>

        <article className="gc-hardware-panel">
          <header>
            <div>
              <span className="gc-hardware-label">
                INSTRUMENTATION
              </span>

              <h3>Sondes de température</h3>
            </div>

            <strong>
              {availableSensors}/4
            </strong>
          </header>

          <div className="gc-hardware-sensors">
            <article
              className={
                validNumber(
                  snapshot?.sourceInTemperature,
                )
                  ? "is-online"
                  : "is-offline"
              }
            >
              <span>01</span>

              <div>
                <strong>
                  Arrivée forage
                </strong>

                <small>
                  Source géothermique entrée
                </small>
              </div>

              <b>
                {formatTemperature(
                  snapshot?.sourceInTemperature,
                )}
              </b>
            </article>

            <article
              className={
                validNumber(
                  snapshot?.sourceOutTemperature,
                )
                  ? "is-online"
                  : "is-offline"
              }
            >
              <span>02</span>

              <div>
                <strong>
                  Retour forage
                </strong>

                <small>
                  Source après échange
                </small>
              </div>

              <b>
                {formatTemperature(
                  snapshot?.sourceOutTemperature,
                )}
              </b>
            </article>

            <article
              className={
                validNumber(
                  snapshot?.supplyTemperature,
                )
                  ? "is-online"
                  : "is-offline"
              }
            >
              <span>03</span>

              <div>
                <strong>
                  Départ plancher
                </strong>

                <small>
                  Eau vers les boucles
                </small>
              </div>

              <b>
                {formatTemperature(
                  snapshot?.supplyTemperature,
                )}
              </b>
            </article>

            <article
              className={
                validNumber(
                  snapshot?.returnTemperature,
                )
                  ? "is-online"
                  : "is-offline"
              }
            >
              <span>04</span>

              <div>
                <strong>
                  Retour plancher
                </strong>

                <small>
                  Eau après échange bâtiment
                </small>
              </div>

              <b>
                {formatTemperature(
                  snapshot?.returnTemperature,
                )}
              </b>
            </article>
          </div>
        </article>
      </section>

      <section className="gc-hardware-checks">
        <header>
          <div>
            <span className="gc-hardware-label">
              CERTIFICATION OPÉRATIONNELLE
            </span>

            <h3>
              Contrôles de disponibilité
            </h3>
          </div>

          <strong>
            {validChecks}/{checks.length}
          </strong>
        </header>

        <div>
          {checks.map((check) => (
            <article
              key={check.id}
              className={
                check.valid
                  ? "is-valid"
                  : check.warning
                    ? "is-warning"
                    : "is-critical"
              }
            >
              <span>
                {check.valid ? "✓" : "!"}
              </span>

              <div>
                <strong>
                  {check.label}
                </strong>

                <small>
                  {check.detail}
                </small>
              </div>
            </article>
          ))}
        </div>
      </section>
    </AppShell>
  );
}
