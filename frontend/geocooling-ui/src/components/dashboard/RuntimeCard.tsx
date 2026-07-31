import type { GeoCoolingSnapshot } from "@/types/geocooling";
import { Metric } from "@/components/ui/Metric";
import { Panel } from "@/components/ui/Panel";
import { StatusBadge } from "@/components/ui/StatusBadge";

type RuntimeCardProps = {
  snapshot: GeoCoolingSnapshot | null;
  lastUpdate: Date | null;
};

function formatDate(value: string | null | undefined): string {
  if (!value) return "Non disponible";

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString("fr-FR", {
    dateStyle: "short",
    timeStyle: "medium",
  });
}

function formatLocalDate(value: Date | null): string {
  if (!value) return "Non disponible";

  return value.toLocaleString("fr-FR", {
    dateStyle: "short",
    timeStyle: "medium",
  });
}

export function RuntimeCard({
  snapshot,
  lastUpdate,
}: RuntimeCardProps) {
  const available = snapshot?.available === true;

  return (
    <Panel
      title="Exploitation"
      subtitle="Synchronisation et qualité des données"
      icon="⌁"
      action={
        <StatusBadge
          label={available ? "DONNÉES DISPONIBLES" : "DONNÉES ABSENTES"}
          tone={available ? "success" : "danger"}
        />
      }
    >
      <div className="gc-metric-grid gc-metric-grid--two">
        <Metric
          label="Disponibilité API"
          value={available ? "OUI" : "NON"}
          tone={available ? "success" : "danger"}
          note="Snapshot du contrôleur"
        />

        <Metric
          label="Télémétrie hydraulique"
          value={
            snapshot?.supplyTemperature !== null &&
            snapshot?.supplyTemperature !== undefined
              ? "ACTIVE"
              : "INCOMPLÈTE"
          }
          tone={
            snapshot?.supplyTemperature !== null &&
            snapshot?.supplyTemperature !== undefined
              ? "success"
              : "warning"
          }
          note="État des mesures terrain"
        />
      </div>

      <dl className="gc-runtime-list">
        <div>
          <dt>Snapshot généré</dt>
          <dd>{formatDate(snapshot?.generatedAt)}</dd>
        </div>

        <div>
          <dt>Reçu par l’interface</dt>
          <dd>{formatLocalDate(lastUpdate)}</dd>
        </div>

        <div>
          <dt>Fréquence automatique</dt>
          <dd>5 secondes</dd>
        </div>
      </dl>
    </Panel>
  );
}
