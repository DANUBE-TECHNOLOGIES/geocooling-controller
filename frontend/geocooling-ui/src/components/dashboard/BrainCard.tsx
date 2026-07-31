import type { GeoCoolingSnapshot } from "@/types/geocooling";
import { Panel } from "@/components/ui/Panel";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { StatusBadge } from "@/components/ui/StatusBadge";

type BrainCardProps = {
  snapshot: GeoCoolingSnapshot | null;
};

function decisionTone(summary: string): "success" | "warning" | "neutral" {
  const normalized = summary.toUpperCase();

  if (normalized.includes("START") || normalized.includes("DÉMARR")) {
    return "success";
  }

  if (normalized.includes("STOP") || normalized.includes("ARRÊT")) {
    return "warning";
  }

  return "neutral";
}

export function BrainCard({ snapshot }: BrainCardProps) {
  const decision = snapshot?.decision;
  const summary = decision?.summary?.trim() || "Aucune décision disponible";
  const reasons = Array.isArray(decision?.reasons)
    ? decision.reasons.filter(Boolean)
    : [];

  return (
    <Panel
      title="GeoCooling Brain"
      subtitle="Décision intelligente et justification"
      icon="◆"
      action={
        <StatusBadge
          label={summary.length > 26 ? "DÉCISION DISPONIBLE" : summary}
          tone={decisionTone(summary)}
        />
      }
    >
      <div className="gc-brain-decision">
        <span className="gc-brain-decision__label">Décision courante</span>
        <p>{summary}</p>
      </div>

      <ProgressBar
        value={decision?.confidence ?? 0}
        label="Confiance du moteur de décision"
      />

      <div className="gc-brain-reasons">
        <span className="gc-brain-reasons__title">Éléments analysés</span>

        {reasons.length > 0 ? (
          <ul>
            {reasons.map((reason, index) => (
              <li key={`${reason}-${index}`}>
                <span aria-hidden="true">✓</span>
                <p>{reason}</p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="gc-empty-message">
            Aucun détail complémentaire transmis par le contrôleur.
          </p>
        )}
      </div>
    </Panel>
  );
}
