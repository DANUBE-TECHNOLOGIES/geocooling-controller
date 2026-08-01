"use client";

import Link from "next/link";

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
