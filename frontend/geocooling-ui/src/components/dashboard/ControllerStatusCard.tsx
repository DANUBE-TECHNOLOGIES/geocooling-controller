import type { GeoCoolingSnapshot } from "@/types/geocooling";
import { Metric } from "@/components/ui/Metric";
import { Panel } from "@/components/ui/Panel";
import { StatusBadge } from "@/components/ui/StatusBadge";

type ControllerStatusCardProps = {
  snapshot: GeoCoolingSnapshot | null;
  connected: boolean;
};

function stateLabel(snapshot: GeoCoolingSnapshot | null): string {
  if (!snapshot) {
    return "INCONNU";
  }

  if (snapshot.pumpRunning || snapshot.valveOpen) {
    return "ACTIF";
  }

  return "ARRÊT";
}

function normalizeMode(snapshot: GeoCoolingSnapshot | null): string {
  return String(snapshot?.mode ?? "INCONNU").toUpperCase();
}

export function ControllerStatusCard({
  snapshot,
  connected,
}: ControllerStatusCardProps) {
  const state = stateLabel(snapshot);
  const mode = normalizeMode(snapshot);
  const manualMode = mode === "MANUAL" || mode === "MANUEL";

  return (
    <Panel
      title="État du contrôleur"
      subtitle="Disponibilité, mode et sécurité"
      icon="◉"
      action={
        <StatusBadge
          label={state}
          tone={state === "ACTIF" ? "success" : "neutral"}
        />
      }
    >
      <div className="gc-metric-grid gc-metric-grid--three">
        <Metric
          label="Backend"
          value={connected ? "EN LIGNE" : "HORS LIGNE"}
          tone={connected ? "success" : "danger"}
          note={
            connected
              ? "Communication opérationnelle"
              : "Aucune donnée reçue"
          }
        />

        <Metric
          label="Mode"
          value={mode}
          tone={manualMode ? "warning" : "info"}
          note="Mode de pilotage courant"
        />

        <Metric
          label="Équipement"
          value={
            snapshot?.deviceReady === true
              ? "PRÊT"
              : snapshot?.deviceReady === false
                ? "NON PRÊT"
                : "INCONNU"
          }
          tone={
            snapshot?.deviceReady === true
              ? "success"
              : snapshot?.deviceReady === false
                ? "danger"
                : "default"
          }
          note="Disponibilité du matériel"
        />
      </div>

      <div className="gc-status-line">
        <div>
          <span className="gc-status-line__label">
            Sécurité générale
          </span>

          <strong>
            {snapshot?.safetySafe === true
              ? "Conditions sûres"
              : snapshot?.safetySafe === false
                ? "Défaut de sécurité"
                : "État inconnu"}
          </strong>
        </div>

        <StatusBadge
          label={
            snapshot?.safetySafe === true
              ? "SÉCURITÉ OK"
              : snapshot?.safetySafe === false
                ? "ALERTE"
                : "INCONNU"
          }
          tone={
            snapshot?.safetySafe === true
              ? "success"
              : snapshot?.safetySafe === false
                ? "danger"
                : "neutral"
          }
        />
      </div>
    </Panel>
  );
}
