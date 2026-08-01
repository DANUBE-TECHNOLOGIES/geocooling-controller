import type { GeoCoolingSnapshot } from "@/types/geocooling";
import { Panel } from "@/components/ui/Panel";
import { StatusBadge } from "@/components/ui/StatusBadge";

type RuntimeCardProps = {
  snapshot: GeoCoolingSnapshot | null;
  lastUpdate: Date | null;
  responseTime: number;
};

type RuntimeState = {
  label: string;
  tone: "success" | "warning" | "danger" | "neutral";
  className: string;
  description: string;
};

function validDate(
  value: string | null | undefined,
): Date | null {
  if (!value) {
    return null;
  }

  const date = new Date(value);

  return Number.isNaN(date.getTime())
    ? null
    : date;
}

function formatDate(
  value: Date | null,
): string {
  if (!value) {
    return "Non disponible";
  }

  return value.toLocaleString("fr-FR", {
    dateStyle: "short",
    timeStyle: "medium",
  });
}

function formatDuration(
  seconds: number | null,
): string {
  if (seconds === null) {
    return "—";
  }

  if (seconds < 60) {
    return `${seconds} s`;
  }

  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;

  return `${minutes} min ${remainingSeconds} s`;
}

function runtimeState(
  snapshot: GeoCoolingSnapshot | null,
  ageSeconds: number | null,
  responseTime: number,
): RuntimeState {
  if (!snapshot?.available) {
    return {
      label: "INDISPONIBLE",
      tone: "danger",
      className: "is-critical",
      description:
        "Le contrôleur ne fournit aucun snapshot exploitable.",
    };
  }

  if (
    ageSeconds === null ||
    ageSeconds > 30
  ) {
    return {
      label: "DONNÉES ANCIENNES",
      tone: "danger",
      className: "is-critical",
      description:
        "Le snapshot reçu n’est plus suffisamment récent.",
    };
  }

  if (
    ageSeconds > 12 ||
    responseTime >= 1500
  ) {
    return {
      label: "DÉGRADÉ",
      tone: "warning",
      className: "is-warning",
      description:
        "La supervision fonctionne avec une fraîcheur ou une latence dégradée.",
    };
  }

  return {
    label: "OPÉRATIONNEL",
    tone: "success",
    className: "is-good",
    description:
      "Les données sont disponibles, récentes et correctement synchronisées.",
  };
}

function latencyState(
  responseTime: number,
): {
  label: string;
  className: string;
} {
  if (responseTime <= 0) {
    return {
      label: "INCONNUE",
      className: "is-neutral",
    };
  }

  if (responseTime < 500) {
    return {
      label: "EXCELLENTE",
      className: "is-good",
    };
  }

  if (responseTime < 1500) {
    return {
      label: "ACCEPTABLE",
      className: "is-warning",
    };
  }

  return {
    label: "ÉLEVÉE",
    className: "is-critical",
  };
}

export function RuntimeCard({
  snapshot,
  lastUpdate,
  responseTime,
}: RuntimeCardProps) {
  const generatedAt =
    validDate(snapshot?.generatedAt);

  const ageSeconds =
    generatedAt && lastUpdate
      ? Math.max(
          0,
          Math.round(
            (
              lastUpdate.getTime() -
              generatedAt.getTime()
            ) / 1000,
          ),
        )
      : null;

  const transportDelay =
    generatedAt && lastUpdate
      ? Math.max(
          0,
          lastUpdate.getTime() -
          generatedAt.getTime(),
        )
      : null;

  const state = runtimeState(
    snapshot,
    ageSeconds,
    responseTime,
  );

  const latency =
    latencyState(responseTime);

  const telemetryAvailable = [
    snapshot?.indoorTemperature,
    snapshot?.humidity,
    snapshot?.sourceInTemperature,
    snapshot?.sourceOutTemperature,
    snapshot?.supplyTemperature,
    snapshot?.returnTemperature,
  ].filter(
    (value) =>
      typeof value === "number" &&
      Number.isFinite(value),
  ).length;

  const telemetryQuality =
    Math.round(
      (telemetryAvailable / 6) * 100,
    );

  return (
    <Panel
      title="Observabilité runtime"
      subtitle="Disponibilité, fraîcheur et performance API"
      icon="⌁"
      className="gc-runtime-console"
      action={
        <StatusBadge
          label={state.label}
          tone={state.tone}
          pulse={state.tone === "success"}
        />
      }
    >
      <section
        className={`gc-runtime-summary ${state.className}`}
      >
        <div className="gc-runtime-summary__icon">
          <span />
        </div>

        <div>
          <span className="gc-runtime-label">
            ÉTAT DE LA SUPERVISION
          </span>

          <strong>
            {state.description}
          </strong>
        </div>
      </section>

      <section className="gc-runtime-kpis">
        <article>
          <header>
            <span className="gc-runtime-label">
              LATENCE API
            </span>

            <strong className={latency.className}>
              {latency.label}
            </strong>
          </header>

          <div>
            <strong>
              {responseTime > 0
                ? responseTime
                : "—"}
            </strong>

            <span>ms</span>
          </div>

          <small>
            Durée de la requête frontend
          </small>
        </article>

        <article>
          <header>
            <span className="gc-runtime-label">
              ÂGE DU SNAPSHOT
            </span>

            <strong
              className={
                ageSeconds === null
                  ? "is-neutral"
                  : ageSeconds <= 12
                    ? "is-good"
                    : ageSeconds <= 30
                      ? "is-warning"
                      : "is-critical"
              }
            >
              {ageSeconds === null
                ? "INCONNU"
                : ageSeconds <= 12
                  ? "RÉCENT"
                  : ageSeconds <= 30
                    ? "RETARDÉ"
                    : "ANCIEN"}
            </strong>
          </header>

          <div>
            <strong>
              {ageSeconds === null
                ? "—"
                : ageSeconds}
            </strong>

            <span>s</span>
          </div>

          <small>
            Écart génération / réception
          </small>
        </article>
      </section>

      <section className="gc-runtime-quality">
        <header>
          <div>
            <span className="gc-runtime-label">
              QUALITÉ TÉLÉMÉTRIE
            </span>

            <strong>
              {telemetryAvailable}/6 mesures
            </strong>
          </div>

          <div>
            <strong>
              {telemetryQuality}
            </strong>

            <span>%</span>
          </div>
        </header>

        <div className="gc-runtime-quality__track">
          <div
            className={
              telemetryQuality >= 85
                ? "is-good"
                : telemetryQuality >= 60
                  ? "is-warning"
                  : "is-critical"
            }
            style={{
              width: `${telemetryQuality}%`,
            }}
          />
        </div>
      </section>

      <dl className="gc-runtime-timeline">
        <div>
          <dt>Snapshot généré</dt>
          <dd>
            {formatDate(generatedAt)}
          </dd>
        </div>

        <div>
          <dt>Reçu par l’interface</dt>
          <dd>
            {formatDate(lastUpdate)}
          </dd>
        </div>

        <div>
          <dt>Délai transport estimé</dt>
          <dd>
            {transportDelay === null
              ? "Non disponible"
              : `${transportDelay} ms`}
          </dd>
        </div>

        <div>
          <dt>Cycle automatique</dt>
          <dd>5 secondes</dd>
        </div>

        <div>
          <dt>Ancienneté courante</dt>
          <dd>
            {formatDuration(ageSeconds)}
          </dd>
        </div>
      </dl>

      <section className="gc-runtime-checks">
        <article
          className={
            snapshot?.available
              ? "is-valid"
              : "is-critical"
          }
        >
          <span>
            {snapshot?.available ? "✓" : "!"}
          </span>

          <div>
            <strong>
              Disponibilité API
            </strong>

            <small>
              {snapshot?.available
                ? "Snapshot disponible"
                : "Aucun snapshot exploitable"}
            </small>
          </div>
        </article>

        <article
          className={
            ageSeconds !== null &&
            ageSeconds <= 30
              ? "is-valid"
              : "is-critical"
          }
        >
          <span>
            {ageSeconds !== null &&
            ageSeconds <= 30
              ? "✓"
              : "!"}
          </span>

          <div>
            <strong>
              Fraîcheur des données
            </strong>

            <small>
              {ageSeconds === null
                ? "Horodatage indisponible"
                : `${ageSeconds} seconde(s)`}
            </small>
          </div>
        </article>

        <article
          className={
            telemetryAvailable === 6
              ? "is-valid"
              : "is-warning"
          }
        >
          <span>
            {telemetryAvailable === 6
              ? "✓"
              : "!"}
          </span>

          <div>
            <strong>
              Complétude télémétrique
            </strong>

            <small>
              {telemetryAvailable}/6 mesures disponibles
            </small>
          </div>
        </article>
      </section>
    </Panel>
  );
}
