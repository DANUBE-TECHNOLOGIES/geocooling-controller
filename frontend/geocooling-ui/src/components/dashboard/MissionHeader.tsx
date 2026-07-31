import type { GeoCoolingSnapshot } from "@/types/geocooling";
import { StatusBadge } from "@/components/ui/StatusBadge";

type MissionHeaderProps = {
  snapshot: GeoCoolingSnapshot | null;
  connected?: boolean;
};

type SystemState = {
  label: string;
  tone: "success" | "warning" | "danger" | "neutral";
  description: string;
};

function formatNumber(
  value: number | null | undefined,
  digits = 1,
): string {
  return typeof value === "number" && Number.isFinite(value)
    ? value.toFixed(digits)
    : "—";
}

function clamp(value: number): number {
  return Math.min(100, Math.max(0, Math.round(value)));
}

function systemState(
  snapshot: GeoCoolingSnapshot | null,
  connected: boolean,
): SystemState {
  if (!connected || !snapshot) {
    return {
      label: "HORS LIGNE",
      tone: "danger",
      description: "Communication avec le contrôleur interrompue",
    };
  }

  if (snapshot.safetySafe === false) {
    return {
      label: "ALARME",
      tone: "danger",
      description: "Une condition de sécurité bloque l’installation",
    };
  }

  if (snapshot.deviceReady === false) {
    return {
      label: "NON PRÊT",
      tone: "warning",
      description: "Le contrôleur ne valide pas la disponibilité matérielle",
    };
  }

  if (snapshot.pumpRunning && snapshot.valveOpen) {
    return {
      label: "RAFRAÎCHISSEMENT",
      tone: "success",
      description: "Le circuit hydraulique est actuellement en fonctionnement",
    };
  }

  if (snapshot.pumpRunning !== snapshot.valveOpen) {
    return {
      label: "TRANSITION",
      tone: "warning",
      description: "Les équipements hydrauliques ne sont pas dans le même état",
    };
  }

  return {
    label: "VEILLE",
    tone: "neutral",
    description: "Installation disponible, circuit hydraulique à l’arrêt",
  };
}

function decisionLabel(summary: string): string {
  const normalized = summary.trim().toUpperCase();

  if (!normalized) {
    return "INDISPONIBLE";
  }

  if (
    normalized.includes("START") ||
    normalized.includes("DÉMARR")
  ) {
    return "DÉMARRAGE";
  }

  if (
    normalized.includes("STOP") ||
    normalized.includes("ARRÊT")
  ) {
    return "ARRÊT";
  }

  if (
    normalized.includes("MAINTIEN") ||
    normalized.includes("HOLD")
  ) {
    return "MAINTIEN";
  }

  return "ANALYSE";
}

export function MissionHeader({
  snapshot,
  connected = Boolean(snapshot?.available),
}: MissionHeaderProps) {
  const state = systemState(snapshot, connected);

  const confidence = clamp(
    snapshot?.decision.confidence ?? 0,
  );

  const indoorTemperature =
    formatNumber(snapshot?.indoorTemperature);

  const humidity =
    formatNumber(snapshot?.humidity);

  const hydraulicDelta =
    typeof snapshot?.returnTemperature === "number" &&
    typeof snapshot.supplyTemperature === "number"
      ? (
          snapshot.returnTemperature -
          snapshot.supplyTemperature
        ).toFixed(1)
      : "—";

  const decision =
    decisionLabel(snapshot?.decision.summary ?? "");

  const hydraulicActive = Boolean(
    snapshot?.pumpRunning &&
    snapshot?.valveOpen &&
    snapshot?.safetySafe !== false,
  );

  return (
    <section className={`gc-mission gc-mission--${state.tone}`}>
      <div className="gc-mission__main">
        <div className="gc-mission__heading">
          <div>
            <p className="gc-mission__eyebrow">
              MISSION CONTROL
            </p>

            <div className="gc-mission__title-row">
              <h2 className="gc-mission__title">
                Supervision GeoCooling
              </h2>

              <StatusBadge
                label={state.label}
                tone={state.tone}
                pulse={state.tone === "success"}
              />
            </div>

            <p className="gc-mission__description">
              {state.description}
            </p>
          </div>

          <div className="gc-mission__brain">
            <span className="gc-mission__brain-label">
              DÉCISION BRAIN
            </span>

            <strong>{decision}</strong>

            <span>
              Confiance {confidence} %
            </span>
          </div>
        </div>

        <div className="gc-mission__confidence">
          <div className="gc-mission__confidence-head">
            <span>Confiance opérationnelle</span>
            <strong>{confidence} %</strong>
          </div>

          <div
            className="gc-mission__confidence-track"
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={confidence}
          >
            <div
              className="gc-mission__confidence-fill"
              style={{ width: `${confidence}%` }}
            />
          </div>
        </div>
      </div>

      <div className="gc-mission__kpis">
        <article className="gc-mission-kpi">
          <span className="gc-mission-kpi__label">
            TEMPÉRATURE
          </span>

          <div className="gc-mission-kpi__value">
            <strong>{indoorTemperature}</strong>
            <span>°C</span>
          </div>

          <small>Ambiance intérieure</small>
        </article>

        <article className="gc-mission-kpi">
          <span className="gc-mission-kpi__label">
            HUMIDITÉ
          </span>

          <div className="gc-mission-kpi__value">
            <strong>{humidity}</strong>
            <span>%</span>
          </div>

          <small>Humidité relative</small>
        </article>

        <article className="gc-mission-kpi">
          <span className="gc-mission-kpi__label">
            DELTA HYDRAULIQUE
          </span>

          <div className="gc-mission-kpi__value">
            <strong>{hydraulicDelta}</strong>
            <span>°C</span>
          </div>

          <small>Retour moins départ</small>
        </article>

        <article className="gc-mission-kpi">
          <span className="gc-mission-kpi__label">
            CIRCUIT
          </span>

          <div
            className={
              hydraulicActive
                ? "gc-mission-kpi__state is-active"
                : "gc-mission-kpi__state is-idle"
            }
          >
            <span />
            <strong>
              {hydraulicActive ? "ACTIF" : "ARRÊT"}
            </strong>
          </div>

          <small>Pompe et électrovanne</small>
        </article>
      </div>
    </section>
  );
}
