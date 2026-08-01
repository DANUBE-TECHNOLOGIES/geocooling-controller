import type { GeoCoolingSnapshot } from "@/types/geocooling";
import { Panel } from "@/components/ui/Panel";
import { StatusBadge } from "@/components/ui/StatusBadge";

type HydraulicCardProps = {
  snapshot: GeoCoolingSnapshot | null;
};

type HydraulicState = {
  label: string;
  tone: "success" | "warning" | "danger" | "neutral";
  className: string;
  description: string;
};

function validNumber(
  value: number | null | undefined,
): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function formatTemperature(
  value: number | null | undefined,
): string {
  return validNumber(value)
    ? value.toFixed(1)
    : "—";
}

function hydraulicState(
  snapshot: GeoCoolingSnapshot | null,
): HydraulicState {
  if (!snapshot) {
    return {
      label: "INCONNU",
      tone: "neutral",
      className: "is-neutral",
      description: "Aucune donnée hydraulique disponible.",
    };
  }

  if (snapshot.safetySafe === false) {
    return {
      label: "BLOQUÉ",
      tone: "danger",
      className: "is-critical",
      description:
        "Une sécurité interdit le fonctionnement hydraulique.",
    };
  }

  if (
    snapshot.pumpRunning &&
    snapshot.valveOpen
  ) {
    return {
      label: "CIRCULATION ACTIVE",
      tone: "success",
      className: "is-running",
      description:
        "L’électrovanne est ouverte et le circulateur fonctionne.",
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
        "Les états de la pompe et de la vanne ne sont pas cohérents.",
    };
  }

  return {
    label: "À L’ARRÊT",
    tone: "neutral",
    className: "is-idle",
    description:
      "Le circuit est disponible mais aucune circulation n’est active.",
  };
}

function deltaState(
  value: number | null,
): {
  label: string;
  className: string;
} {
  if (value === null) {
    return {
      label: "INCONNU",
      className: "is-neutral",
    };
  }

  const absolute = Math.abs(value);

  if (absolute < 0.3) {
    return {
      label: "TRÈS FAIBLE",
      className: "is-warning",
    };
  }

  if (absolute <= 4) {
    return {
      label: "COHÉRENT",
      className: "is-good",
    };
  }

  return {
    label: "ÉLEVÉ",
    className: "is-warning",
  };
}

export function HydraulicCard({
  snapshot,
}: HydraulicCardProps) {
  const running =
    snapshot?.pumpRunning === true;

  const valveOpen =
    snapshot?.valveOpen === true;

  const state = hydraulicState(snapshot);

  const sourceDelta =
    validNumber(snapshot?.sourceInTemperature) &&
    validNumber(snapshot?.sourceOutTemperature)
      ? snapshot.sourceOutTemperature -
        snapshot.sourceInTemperature
      : null;

  const floorDelta =
    validNumber(snapshot?.supplyTemperature) &&
    validNumber(snapshot?.returnTemperature)
      ? snapshot.returnTemperature -
        snapshot.supplyTemperature
      : null;

  const sourceDeltaState =
    deltaState(sourceDelta);

  const floorDeltaState =
    deltaState(floorDelta);

  const availableSensors = [
    snapshot?.sourceInTemperature,
    snapshot?.sourceOutTemperature,
    snapshot?.supplyTemperature,
    snapshot?.returnTemperature,
  ].filter(validNumber).length;

  const sequenceCoherent =
    running === valveOpen;

  return (
    <Panel
      title="Diagnostic hydraulique"
      subtitle="Équipements, échange thermique et cohérence"
      icon="≈"
      className="gc-hydraulic-console"
      action={
        <StatusBadge
          label={state.label}
          tone={state.tone}
          pulse={state.tone === "success"}
        />
      }
    >
      <section
        className={`gc-hydraulic-status ${state.className}`}
      >
        <div className="gc-hydraulic-status__symbol">
          <span
            className={
              running
                ? "is-running"
                : ""
            }
          >
            ⟳
          </span>
        </div>

        <div>
          <span className="gc-hydraulic-label">
            ÉTAT DU CIRCUIT
          </span>

          <strong>{state.description}</strong>
        </div>
      </section>

      <section className="gc-hydraulic-sequence">
        <article
          className={
            valveOpen
              ? "gc-hydraulic-device is-active"
              : "gc-hydraulic-device is-idle"
          }
        >
          <div className="gc-hydraulic-device__head">
            <span className="gc-hydraulic-label">
              ÉLECTROVANNE
            </span>

            <i />
          </div>

          <strong>
            {valveOpen ? "OUVERTE" : "FERMÉE"}
          </strong>

          <small>
            Autorisation de circulation
          </small>
        </article>

        <div
          className={
            valveOpen
              ? "gc-hydraulic-link is-active"
              : "gc-hydraulic-link"
          }
          aria-hidden="true"
        >
          <span />
          <span />
          <span />
        </div>

        <article
          className={
            running
              ? "gc-hydraulic-device is-active"
              : "gc-hydraulic-device is-idle"
          }
        >
          <div className="gc-hydraulic-device__head">
            <span className="gc-hydraulic-label">
              CIRCULATEUR
            </span>

            <i />
          </div>

          <strong>
            {running ? "EN MARCHE" : "ARRÊTÉ"}
          </strong>

          <small>
            Circulation vers le plancher
          </small>
        </article>
      </section>

      <section className="gc-hydraulic-deltas">
        <article>
          <header>
            <span className="gc-hydraulic-label">
              ÉCHANGE SOURCE
            </span>

            <strong
              className={sourceDeltaState.className}
            >
              {sourceDeltaState.label}
            </strong>
          </header>

          <div className="gc-hydraulic-delta-value">
            <strong>
              {sourceDelta === null
                ? "—"
                : sourceDelta.toFixed(1)}
            </strong>

            <span>°C</span>
          </div>

          <div className="gc-hydraulic-temperature-pair">
            <div>
              <span>ENTRÉE</span>
              <strong>
                {formatTemperature(
                  snapshot?.sourceInTemperature,
                )} °C
              </strong>
            </div>

            <div>
              <span>SORTIE</span>
              <strong>
                {formatTemperature(
                  snapshot?.sourceOutTemperature,
                )} °C
              </strong>
            </div>
          </div>
        </article>

        <article>
          <header>
            <span className="gc-hydraulic-label">
              ÉCHANGE PLANCHER
            </span>

            <strong
              className={floorDeltaState.className}
            >
              {floorDeltaState.label}
            </strong>
          </header>

          <div className="gc-hydraulic-delta-value">
            <strong>
              {floorDelta === null
                ? "—"
                : floorDelta.toFixed(1)}
            </strong>

            <span>°C</span>
          </div>

          <div className="gc-hydraulic-temperature-pair">
            <div>
              <span>DÉPART</span>
              <strong>
                {formatTemperature(
                  snapshot?.supplyTemperature,
                )} °C
              </strong>
            </div>

            <div>
              <span>RETOUR</span>
              <strong>
                {formatTemperature(
                  snapshot?.returnTemperature,
                )} °C
              </strong>
            </div>
          </div>
        </article>
      </section>

      <section className="gc-hydraulic-diagnostics">
        <header>
          <span className="gc-hydraulic-label">
            CONTRÔLES DE COHÉRENCE
          </span>

          <strong>
            {sequenceCoherent ? "3/3" : "2/3"}
          </strong>
        </header>

        <div>
          <article
            className={
              sequenceCoherent
                ? "is-valid"
                : "is-warning"
            }
          >
            <span>
              {sequenceCoherent ? "✓" : "!"}
            </span>

            <div>
              <strong>
                Séquence pompe / vanne
              </strong>

              <small>
                {sequenceCoherent
                  ? "États hydrauliques cohérents"
                  : "Équipement en transition ou défaut"}
              </small>
            </div>
          </article>

          <article
            className={
              snapshot?.safetySafe === false
                ? "is-critical"
                : "is-valid"
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
                  ? "Sécurité bloquante active"
                  : "Aucun blocage signalé"}
              </small>
            </div>
          </article>

          <article
            className={
              availableSensors === 4
                ? "is-valid"
                : "is-warning"
            }
          >
            <span>
              {availableSensors === 4
                ? "✓"
                : "!"}
            </span>

            <div>
              <strong>
                Instrumentation
              </strong>

              <small>
                {availableSensors}/4 sondes disponibles
              </small>
            </div>
          </article>
        </div>
      </section>

      <footer className="gc-hydraulic-footer">
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
              sequenceCoherent
                ? "is-positive"
                : "is-warning"
            }
          />

          Séquence
          {sequenceCoherent
            ? " cohérente"
            : " transitoire"}
        </div>

        <div>
          <span
            className={
              availableSensors === 4
                ? "is-positive"
                : "is-warning"
            }
          />

          Sondes {availableSensors}/4
        </div>
      </footer>
    </Panel>
  );
}
