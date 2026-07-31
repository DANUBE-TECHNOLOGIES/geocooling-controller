import type { GeoCoolingSnapshot } from "@/types/geocooling";
import { Panel } from "@/components/ui/Panel";
import { StatusBadge } from "@/components/ui/StatusBadge";

type BrainCardProps = {
  snapshot: GeoCoolingSnapshot | null;
};

type DecisionState = {
  code: string;
  label: string;
  tone: "success" | "warning" | "danger" | "info" | "neutral";
  description: string;
};

type DataCriterion = {
  label: string;
  available: boolean;
  detail: string;
};

function clamp(value: number): number {
  return Math.max(0, Math.min(100, Math.round(value)));
}

function decisionState(summary: string): DecisionState {
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
        "Le Brain recommande l’activation du rafraîchissement.",
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
    normalized.includes("ALARM") ||
    normalized.includes("ALARME") ||
    normalized.includes("DÉFAUT")
  ) {
    return {
      code: "ALARM",
      label: "SÉCURITÉ",
      tone: "danger",
      description:
        "La stratégie est limitée par une condition de sécurité.",
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
        "Le Brain conserve la stratégie opérationnelle actuelle.",
    };
  }

  return {
    code: "ANALYSE",
    label: "ANALYSE",
    tone: "neutral",
    description:
      "Le Brain analyse les conditions disponibles.",
  };
}

function confidenceState(value: number): {
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

function formatValue(
  value: number | null | undefined,
  unit: string,
): string {
  return typeof value === "number" && Number.isFinite(value)
    ? `${value.toFixed(1)} ${unit}`
    : "Non mesuré";
}

function buildCriteria(
  snapshot: GeoCoolingSnapshot | null,
): DataCriterion[] {
  return [
    {
      label: "Ambiance intérieure",
      available:
        typeof snapshot?.indoorTemperature === "number",
      detail: formatValue(
        snapshot?.indoorTemperature,
        "°C",
      ),
    },
    {
      label: "Humidité relative",
      available:
        typeof snapshot?.humidity === "number",
      detail: formatValue(
        snapshot?.humidity,
        "%",
      ),
    },
    {
      label: "Source géothermique",
      available:
        typeof snapshot?.sourceInTemperature === "number",
      detail: formatValue(
        snapshot?.sourceInTemperature,
        "°C",
      ),
    },
    {
      label: "Départ plancher",
      available:
        typeof snapshot?.supplyTemperature === "number",
      detail: formatValue(
        snapshot?.supplyTemperature,
        "°C",
      ),
    },
    {
      label: "Retour plancher",
      available:
        typeof snapshot?.returnTemperature === "number",
      detail: formatValue(
        snapshot?.returnTemperature,
        "°C",
      ),
    },
    {
      label: "Sécurité",
      available:
        snapshot?.safetySafe !== null &&
        snapshot?.safetySafe !== undefined,
      detail:
        snapshot?.safetySafe === true
          ? "Conditions validées"
          : snapshot?.safetySafe === false
            ? "Blocage sécurité"
            : "État inconnu",
    },
  ];
}

export function BrainCard({
  snapshot,
}: BrainCardProps) {
  const decision = snapshot?.decision;

  const summary =
    decision?.summary?.trim() ||
    "Aucune explication disponible.";

  const reasons = Array.isArray(decision?.reasons)
    ? decision.reasons
        .map((reason) => reason.trim())
        .filter(Boolean)
    : [];

  const confidence = clamp(
    decision?.confidence ?? 0,
  );

  const state = decisionState(summary);
  const confidenceLevel =
    confidenceState(confidence);

  const criteria = buildCriteria(snapshot);

  const availableCriteria =
    criteria.filter(
      (criterion) => criterion.available,
    ).length;

  const dataQuality = Math.round(
    (availableCriteria / criteria.length) * 100,
  );

  const hydraulicCoherent =
    snapshot !== null &&
    snapshot.pumpRunning === snapshot.valveOpen;

  return (
    <Panel
      title="GeoCooling Brain"
      subtitle="Décision, confiance et données analysées"
      icon="◆"
      className="gc-brain-console"
      action={
        <StatusBadge
          label={state.label}
          tone={state.tone}
          pulse={state.tone === "success"}
        />
      }
    >
      <section className="gc-brain-console__decision">
        <div className="gc-brain-console__decision-code">
          <span>DÉCISION COURANTE</span>
          <strong>{state.code}</strong>
        </div>

        <div className="gc-brain-console__decision-text">
          <strong>{state.description}</strong>
          <p>{summary}</p>
        </div>
      </section>

      <section className="gc-brain-console__gauges">
        <article className="gc-brain-gauge">
          <header>
            <span>CONFIANCE</span>

            <strong
              className={confidenceLevel.className}
            >
              {confidenceLevel.label}
            </strong>
          </header>

          <div className="gc-brain-gauge__value">
            <strong>{confidence}</strong>
            <span>%</span>
          </div>

          <div className="gc-brain-gauge__track">
            <div
              className={`gc-brain-gauge__fill ${confidenceLevel.className}`}
              style={{ width: `${confidence}%` }}
            />
          </div>
        </article>

        <article className="gc-brain-gauge">
          <header>
            <span>QUALITÉ DONNÉES</span>

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

          <div className="gc-brain-gauge__value">
            <strong>{dataQuality}</strong>
            <span>%</span>
          </div>

          <div className="gc-brain-gauge__track">
            <div
              className={
                dataQuality >= 80
                  ? "gc-brain-gauge__fill is-good"
                  : dataQuality >= 50
                    ? "gc-brain-gauge__fill is-warning"
                    : "gc-brain-gauge__fill is-critical"
              }
              style={{ width: `${dataQuality}%` }}
            />
          </div>
        </article>
      </section>

      <section className="gc-brain-console__criteria">
        <header>
          <span>DONNÉES DISPONIBLES</span>

          <strong>
            {availableCriteria}/{criteria.length}
          </strong>
        </header>

        <div className="gc-brain-criteria-grid">
          {criteria.map((criterion) => (
            <article
              key={criterion.label}
              className={
                criterion.available
                  ? "gc-brain-criterion is-available"
                  : "gc-brain-criterion is-missing"
              }
            >
              <span
                className="gc-brain-criterion__state"
                aria-hidden="true"
              >
                {criterion.available ? "✓" : "–"}
              </span>

              <div>
                <strong>{criterion.label}</strong>
                <small>{criterion.detail}</small>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="gc-brain-console__reasons">
        <header>
          <span>JUSTIFICATION DU BRAIN</span>
          <strong>{reasons.length}</strong>
        </header>

        {reasons.length > 0 ? (
          <ol>
            {reasons.map((reason, index) => (
              <li key={`${reason}-${index}`}>
                <span>
                  {String(index + 1).padStart(2, "0")}
                </span>

                <p>{reason}</p>
              </li>
            ))}
          </ol>
        ) : (
          <p className="gc-brain-console__empty">
            Aucun critère explicatif détaillé
            n’a été transmis.
          </p>
        )}
      </section>

      <footer className="gc-brain-console__footer">
        <div>
          <span
            className={
              snapshot?.deviceReady
                ? "is-positive"
                : "is-neutral"
            }
          />

          Contrôleur
          {snapshot?.deviceReady
            ? " prêt"
            : " non prêt"}
        </div>

        <div>
          <span
            className={
              hydraulicCoherent
                ? "is-positive"
                : "is-warning"
            }
          />

          Hydraulique
          {hydraulicCoherent
            ? " cohérente"
            : " en transition"}
        </div>

        <div>
          <span
            className={
              snapshot?.safetySafe === false
                ? "is-negative"
                : "is-positive"
            }
          />

          Sécurité
          {snapshot?.safetySafe === false
            ? " bloquante"
            : " validée"}
        </div>
      </footer>
    </Panel>
  );
}
