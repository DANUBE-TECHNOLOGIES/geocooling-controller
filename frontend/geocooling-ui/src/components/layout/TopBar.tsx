import { StatusBadge } from "@/components/ui/StatusBadge";

type TopBarProps = {
  connected: boolean;
  mode: string;
  refreshing: boolean;
  lastUpdate: Date | null;
  generatedAt?: string | null;
  responseTime?: number;
  onRefresh: () => void;
};

function formatTime(date: Date | null): string {
  if (!date) {
    return "--:--:--";
  }

  return date.toLocaleTimeString("fr-FR", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function normalizeMode(mode: string): {
  label: string;
  tone: "success" | "warning" | "info" | "neutral";
} {
  switch (mode.trim().toLowerCase()) {
    case "automatic":
    case "automatique":
      return {
        label: "AUTOMATIQUE",
        tone: "success",
      };

    case "manual":
    case "manuel":
      return {
        label: "MANUEL",
        tone: "warning",
      };

    case "simulation":
      return {
        label: "SIMULATION",
        tone: "info",
      };

    default:
      return {
        label: "INCONNU",
        tone: "neutral",
      };
  }
}

function latencyState(responseTime: number): {
  label: string;
  className: string;
} {
  if (responseTime <= 0) {
    return {
      label: "-- ms",
      className: "gc-supervision-value is-neutral",
    };
  }

  if (responseTime < 500) {
    return {
      label: `${responseTime} ms`,
      className: "gc-supervision-value is-good",
    };
  }

  if (responseTime < 1500) {
    return {
      label: `${responseTime} ms`,
      className: "gc-supervision-value is-warning",
    };
  }

  return {
    label: `${responseTime} ms`,
    className: "gc-supervision-value is-critical",
  };
}

function snapshotState(
  generatedAt: string | null | undefined,
  lastUpdate: Date | null,
): {
  label: string;
  className: string;
} {
  if (!generatedAt || !lastUpdate) {
    return {
      label: "INCONNU",
      className: "gc-supervision-value is-neutral",
    };
  }

  const generated = new Date(generatedAt);

  if (Number.isNaN(generated.getTime())) {
    return {
      label: "INVALIDE",
      className: "gc-supervision-value is-critical",
    };
  }

  const ageSeconds = Math.max(
    0,
    Math.round((lastUpdate.getTime() - generated.getTime()) / 1000),
  );

  if (ageSeconds <= 15) {
    return {
      label: `${ageSeconds} s`,
      className: "gc-supervision-value is-good",
    };
  }

  if (ageSeconds <= 60) {
    return {
      label: `${ageSeconds} s`,
      className: "gc-supervision-value is-warning",
    };
  }

  return {
    label: `${ageSeconds} s`,
    className: "gc-supervision-value is-critical",
  };
}

export function TopBar({
  connected,
  mode,
  refreshing,
  lastUpdate,
  generatedAt = null,
  responseTime = 0,
  onRefresh,
}: TopBarProps) {
  const normalizedMode = normalizeMode(mode);
  const latency = latencyState(responseTime);
  const snapshot = snapshotState(generatedAt, lastUpdate);

  return (
    <header className="gc-topbar gc-topbar--enterprise">
      <div className="gc-topbar__identity">
        <div className="gc-logo" aria-hidden="true">
          GC
        </div>

        <div>
          <p className="gc-topbar__eyebrow">
            SMART BUILDING CONTROLLER
          </p>

          <h1 className="gc-topbar__title">
            GeoCooling Enterprise
          </h1>
        </div>
      </div>

      <div
        className="gc-supervision-strip"
        aria-label="État de la supervision"
      >
        <div className="gc-supervision-item">
          <span className="gc-supervision-label">BACKEND</span>

          <StatusBadge
            label={connected ? "CONNECTÉ" : "HORS LIGNE"}
            tone={connected ? "success" : "danger"}
            pulse={connected}
          />
        </div>

        <div className="gc-supervision-item">
          <span className="gc-supervision-label">MODE</span>

          <StatusBadge
            label={normalizedMode.label}
            tone={normalizedMode.tone}
          />
        </div>

        <div className="gc-supervision-item">
          <span className="gc-supervision-label">LATENCE API</span>
          <strong className={latency.className}>{latency.label}</strong>
        </div>

        <div className="gc-supervision-item">
          <span className="gc-supervision-label">ÂGE SNAPSHOT</span>
          <strong className={snapshot.className}>{snapshot.label}</strong>
        </div>

        <div className="gc-supervision-item">
          <span className="gc-supervision-label">DERNIÈRE MAJ</span>
          <strong className="gc-supervision-value">
            {formatTime(lastUpdate)}
          </strong>
        </div>

        <button
          className="gc-refresh-button gc-refresh-button--compact"
          type="button"
          onClick={onRefresh}
          disabled={refreshing}
          aria-label="Actualiser les données GeoCooling"
        >
          <span
            className={
              refreshing
                ? "gc-refresh-icon is-spinning"
                : "gc-refresh-icon"
            }
            aria-hidden="true"
          >
            ↻
          </span>

          <span>
            {refreshing ? "SYNC…" : "ACTUALISER"}
          </span>
        </button>
      </div>
    </header>
  );
}
