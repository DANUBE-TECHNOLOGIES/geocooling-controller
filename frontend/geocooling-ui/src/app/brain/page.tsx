"use client";

import Link from "next/link";
import type { GeoCoolingSnapshot } from "@/types/geocooling";
import { AppShell } from "@/components/layout/AppShell";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useGeoCooling } from "@/hooks/useGeoCooling";

type DecisionState = {
  code: string;
  label: string;
  tone: "success" | "warning" | "danger" | "info" | "neutral";
  description: string;
};

type Criterion = {
  label: string;
  detail: string;
  available: boolean;
  positive: boolean;
};

function validNumber(
  value: number | null | undefined,
): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function clamp(value: number): number {
  return Math.max(0, Math.min(100, Math.round(value)));
}

function formatValue(
  value: number | null | undefined,
  unit: string,
): string {
  return validNumber(value)
    ? `${value.toFixed(1)} ${unit}`
    : "Non disponible";
}

function decisionState(
  summary: string,
): DecisionState {
  const normalized = summary.trim().toUpperCase();

  if (
    normalized.includes("START") ||
    normalized.includes("DÉMARR")
  ) {
    return {
      code: "START",
      label: "DÉMARRAGE",
      tone: "success",
      description:
        "Le Brain recommande l’activation du circuit GeoCooling.",
    };
  }

  if (
    normalized.includes("STOP") ||
    normalized.includes("ARRÊT")
  ) {
    return {
      code: "STOP",
      label: "ARRÊT",
      tone: "warning",
      description:
        "Le Brain recommande l’arrêt ou le maintien à l’arrêt.",
    };
  }

  if (
    normalized.includes("HOLD") ||
    normalized.includes("MAINTIEN")
  ) {
    return {
      code: "HOLD",
      label: "MAINTIEN",
      tone: "info",
      description:
        "Le Brain conserve la stratégie actuelle.",
    };
  }

  if (
    normalized.includes("ALARME") ||
    normalized.includes("ALARM") ||
    normalized.includes("DÉFAUT")
  ) {
    return {
      code: "SAFE",
      label: "SÉCURITÉ",
      tone: "danger",
      description:
        "La stratégie est limitée par une condition de sécurité.",
    };
  }

  return {
    code: "ANALYSE",
    label: "ANALYSE",
    tone: "neutral",
    description:
      "Le Brain analyse les données disponibles.",
  };
}

function confidenceState(
  value: number,
): {
  label: string;
  className: string;
} {
  if (value >= 85) {
    return {
      label: "ÉLEVÉE",
      className: "is-good",
    };
  }

  if (value >= 60) {
    return {
      label: "MODÉRÉE",
      className: "is-warning",
    };
  }

  return {
    label: "FAIBLE",
    className: "is-critical",
  };
}

function buildCriteria(
  snapshot: GeoCoolingSnapshot | null,
): Criterion[] {
  return [
    {
      label: "Température intérieure",
      detail: formatValue(
        snapshot?.indoorTemperature,
        "°C",
      ),
      available:
        validNumber(snapshot?.indoorTemperature),
      positive:
        validNumber(snapshot?.indoorTemperature) &&
        snapshot.indoorTemperature >= 24,
    },
    {
      label: "Humidité intérieure",
      detail: formatValue(
        snapshot?.humidity,
        "%",
      ),
      available:
        validNumber(snapshot?.humidity),
      positive:
        validNumber(snapshot?.humidity) &&
        snapshot.humidity <= 65,
    },
    {
      label: "Source géothermique",
      detail: formatValue(
        snapshot?.sourceInTemperature,
        "°C",
      ),
      available:
        validNumber(snapshot?.sourceInTemperature),
      positive:
        validNumber(snapshot?.sourceInTemperature),
    },
    {
      label: "Départ plancher",
      detail: formatValue(
        snapshot?.supplyTemperature,
        "°C",
      ),
      available:
        validNumber(snapshot?.supplyTemperature),
      positive:
        validNumber(snapshot?.supplyTemperature),
    },
    {
      label: "Sécurité générale",
      detail:
        snapshot?.safetySafe === true
          ? "Conditions validées"
          : snapshot?.safetySafe === false
            ? "Blocage sécurité"
            : "État inconnu",
      available:
        snapshot?.safetySafe !== null &&
        snapshot?.safetySafe !== undefined,
      positive:
        snapshot?.safetySafe === true,
    },
    {
      label: "Disponibilité matérielle",
      detail:
        snapshot?.deviceReady === true
          ? "Contrôleur prêt"
          : snapshot?.deviceReady === false
            ? "Contrôleur non prêt"
            : "État inconnu",
      available:
        snapshot?.deviceReady !== null &&
        snapshot?.deviceReady !== undefined,
      positive:
        snapshot?.deviceReady === true,
    },
  ];
}

export default function BrainPage() {
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

  const summary =
    snapshot?.decision.summary?.trim() ||
    "Aucune décision détaillée transmise.";

  const reasons = Array.isArray(
    snapshot?.decision.reasons,
  )
    ? snapshot!.decision.reasons
        .map((reason) => reason.trim())
        .filter(Boolean)
    : [];

  const confidence = clamp(
    snapshot?.decision.confidence ?? 0,
  );

  const decision = decisionState(summary);
  const confidenceLevel =
    confidenceState(confidence);

  const criteria = buildCriteria(snapshot);

  const availableCriteria =
    criteria.filter(
      (criterion) => criterion.available,
    ).length;

  const positiveCriteria =
    criteria.filter(
      (criterion) =>
        criterion.available &&
        criterion.positive,
    ).length;

  const dataQuality = Math.round(
    (availableCriteria / criteria.length) * 100,
  );

  const hydraulicCoherent =
    snapshot !== null &&
    snapshot.pumpRunning === snapshot.valveOpen;

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
            INTELLIGENCE OPÉRATIONNELLE
          </p>

          <h2>GeoCooling Brain</h2>

          <p>
            Analyse de la décision courante, de sa
            confiance, des critères disponibles et
            de la cohérence avec les équipements.
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
            label={decision.label}
            tone={decision.tone}
            pulse={decision.tone === "success"}
          />
        </div>
      </section>

      {loading && !snapshot ? (
        <section className="gc-loading-state">
          <div className="gc-loading-spinner" />

          <div>
            <strong>
              Chargement du Brain…
            </strong>

            <span>
              Analyse du premier snapshot.
            </span>
          </div>
        </section>
      ) : null}

      <section className="gc-brain-page-grid">
        <article className="gc-brain-page-decision">
          <header>
            <div>
              <span className="gc-brain-page-label">
                DÉCISION COURANTE
              </span>

              <strong>{decision.code}</strong>
            </div>

            <StatusBadge
              label={decision.label}
              tone={decision.tone}
            />
          </header>

          <h3>
            {decision.description}
          </h3>

          <p>{summary}</p>

          <div className="gc-brain-page-decision__footer">
            <span>
              Mode :{" "}
              <strong>
                {String(
                  snapshot?.mode ?? "INCONNU",
                ).toUpperCase()}
              </strong>
            </span>

            <span>
              Circuit :{" "}
              <strong>
                {snapshot?.pumpRunning &&
                snapshot?.valveOpen
                  ? "ACTIF"
                  : "ARRÊT"}
              </strong>
            </span>
          </div>
        </article>

        <article className="gc-brain-page-confidence">
          <header>
            <span className="gc-brain-page-label">
              CONFIANCE
            </span>

            <strong
              className={confidenceLevel.className}
            >
              {confidenceLevel.label}
            </strong>
          </header>

          <div className="gc-brain-page-confidence__value">
            <strong>{confidence}</strong>
            <span>%</span>
          </div>

          <div className="gc-brain-page-progress">
            <div
              className={confidenceLevel.className}
              style={{
                width: `${confidence}%`,
              }}
            />
          </div>

          <small>
            Score transmis par le moteur de décision.
          </small>
        </article>

        <article className="gc-brain-page-confidence">
          <header>
            <span className="gc-brain-page-label">
              QUALITÉ DES DONNÉES
            </span>

            <strong
              className={
                dataQuality >= 80
                  ? "is-good"
                  : dataQuality >= 50
                    ? "is-warning"
                    : "is-critical"
              }
            >
              {availableCriteria}/{criteria.length}
            </strong>
          </header>

          <div className="gc-brain-page-confidence__value">
            <strong>{dataQuality}</strong>
            <span>%</span>
          </div>

          <div className="gc-brain-page-progress">
            <div
              className={
                dataQuality >= 80
                  ? "is-good"
                  : dataQuality >= 50
                    ? "is-warning"
                    : "is-critical"
              }
              style={{
                width: `${dataQuality}%`,
              }}
            />
          </div>

          <small>
            Complétude des mesures utilisées.
          </small>
        </article>
      </section>

      <section className="gc-brain-analysis">
        <article className="gc-brain-analysis__criteria">
          <header>
            <div>
              <span className="gc-brain-page-label">
                MATRICE DE DÉCISION
              </span>

              <h3>
                Critères analysés
              </h3>
            </div>

            <strong>
              {positiveCriteria}/{availableCriteria}
            </strong>
          </header>

          <div>
            {criteria.map((criterion) => (
              <article
                key={criterion.label}
                className={
                  !criterion.available
                    ? "is-missing"
                    : criterion.positive
                      ? "is-positive"
                      : "is-warning"
                }
              >
                <span>
                  {!criterion.available
                    ? "–"
                    : criterion.positive
                      ? "✓"
                      : "!"}
                </span>

                <div>
                  <strong>
                    {criterion.label}
                  </strong>

                  <small>
                    {criterion.detail}
                  </small>
                </div>
              </article>
            ))}
          </div>
        </article>

        <article className="gc-brain-analysis__reasons">
          <header>
            <div>
              <span className="gc-brain-page-label">
                EXPLICATION
              </span>

              <h3>
                Justification du Brain
              </h3>
            </div>

            <strong>{reasons.length}</strong>
          </header>

          {reasons.length > 0 ? (
            <ol>
              {reasons.map((reason, index) => (
                <li key={`${reason}-${index}`}>
                  <span>
                    {String(index + 1).padStart(
                      2,
                      "0",
                    )}
                  </span>

                  <p>{reason}</p>
                </li>
              ))}
            </ol>
          ) : (
            <div className="gc-brain-analysis__empty">
              Aucun motif détaillé supplémentaire
              n’a été transmis.
            </div>
          )}
        </article>
      </section>

      <section className="gc-brain-coherence">
        <header>
          <div>
            <span className="gc-brain-page-label">
              VALIDATION OPÉRATIONNELLE
            </span>

            <h3>
              Cohérence décision / terrain
            </h3>
          </div>
        </header>

        <div>
          <article
            className={
              connected
                ? "is-positive"
                : "is-critical"
            }
          >
            <span>
              {connected ? "✓" : "!"}
            </span>

            <div>
              <strong>
                Communication backend
              </strong>

              <small>
                {connected
                  ? "Snapshot disponible"
                  : "Données indisponibles"}
              </small>
            </div>
          </article>

          <article
            className={
              snapshot?.deviceReady
                ? "is-positive"
                : "is-warning"
            }
          >
            <span>
              {snapshot?.deviceReady
                ? "✓"
                : "!"}
            </span>

            <div>
              <strong>
                Disponibilité matérielle
              </strong>

              <small>
                {snapshot?.deviceReady
                  ? "Contrôleur prêt"
                  : "Contrôleur non prêt"}
              </small>
            </div>
          </article>

          <article
            className={
              snapshot?.safetySafe === false
                ? "is-critical"
                : "is-positive"
            }
          >
            <span>
              {snapshot?.safetySafe === false
                ? "!"
                : "✓"}
            </span>

            <div>
              <strong>
                Sécurité générale
              </strong>

              <small>
                {snapshot?.safetySafe === false
                  ? "Blocage actif"
                  : "Conditions validées"}
              </small>
            </div>
          </article>

          <article
            className={
              hydraulicCoherent
                ? "is-positive"
                : "is-warning"
            }
          >
            <span>
              {hydraulicCoherent
                ? "✓"
                : "!"}
            </span>

            <div>
              <strong>
                Séquence hydraulique
              </strong>

              <small>
                {hydraulicCoherent
                  ? "Pompe et vanne cohérentes"
                  : "Transition détectée"}
              </small>
            </div>
          </article>
        </div>
      </section>
    </AppShell>
  );
}
