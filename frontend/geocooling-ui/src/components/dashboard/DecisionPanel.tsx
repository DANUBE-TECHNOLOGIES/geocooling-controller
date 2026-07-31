import type { BrainDecision } from "@/types/geocooling";

function clampConfidence(value: number): number {
  return Math.max(0, Math.min(100, Math.round(value)));
}

function confidenceClass(value: number): string {
  if (value >= 85) return "brain-v2-confidence brain-v2-confidence-good";
  if (value >= 65) return "brain-v2-confidence brain-v2-confidence-warning";
  return "brain-v2-confidence brain-v2-confidence-critical";
}

function decisionState(summary: string): {
  label: string;
  className: string;
} {
  const normalized = summary.toLowerCase();

  if (
    normalized.includes("arrêt") ||
    normalized.includes("stop") ||
    normalized.includes("désactiv")
  ) {
    return {
      label: "ARRÊT",
      className: "brain-v2-state brain-v2-state-idle",
    };
  }

  if (
    normalized.includes("alarme") ||
    normalized.includes("défaut") ||
    normalized.includes("sécurité")
  ) {
    return {
      label: "VIGILANCE",
      className: "brain-v2-state brain-v2-state-warning",
    };
  }

  return {
    label: "ACTIF",
    className: "brain-v2-state brain-v2-state-active",
  };
}

export function DecisionPanel({
  decision,
}: {
  decision: BrainDecision;
}) {
  const confidence = clampConfidence(decision.confidence);
  const state = decisionState(decision.summary);
  const reasons = Array.isArray(decision.reasons)
    ? decision.reasons.filter((reason) => reason.trim().length > 0)
    : [];

  return (
    <article className="panel brain-v2-panel">
      <header className="brain-v2-header">
        <div>
          <div className="brain-v2-kicker">INTELLIGENCE DE PILOTAGE</div>
          <h2 className="brain-v2-title">GeoCooling Brain</h2>
          <p className="brain-v2-subtitle">
            Analyse en temps réel de la situation thermique et hydraulique.
          </p>
        </div>

        <div
          className={confidenceClass(confidence)}
          aria-label={`Confiance ${confidence} pour cent`}
        >
          <span className="brain-v2-confidence-value">{confidence}</span>
          <span className="brain-v2-confidence-unit">%</span>
          <span className="brain-v2-confidence-label">CONFIANCE</span>
        </div>
      </header>

      <section className="brain-v2-status-grid" aria-label="État du Brain">
        <div className="brain-v2-status-card">
          <span className="brain-v2-status-label">ÉTAT</span>
          <span className={state.className}>
            <span className="brain-v2-state-dot" />
            {state.label}
          </span>
        </div>

        <div className="brain-v2-status-card">
          <span className="brain-v2-status-label">ANALYSE</span>
          <span className="brain-v2-status-value">
            {reasons.length} critère{reasons.length > 1 ? "s" : ""}
          </span>
        </div>
      </section>

      <section className="brain-v2-decision">
        <div className="brain-v2-section-label">DÉCISION COURANTE</div>
        <div className="brain-v2-decision-content">
          <span className="brain-v2-decision-icon" aria-hidden="true">◎</span>
          <p>{decision.summary || "Aucune décision disponible."}</p>
        </div>
      </section>

      <section className="brain-v2-reasons">
        <div className="brain-v2-section-head">
          <span className="brain-v2-section-label">CRITÈRES UTILISÉS</span>
          <span className="brain-v2-reasons-count">{reasons.length}</span>
        </div>

        {reasons.length === 0 ? (
          <div className="brain-v2-empty">
            Le contrôleur n’a fourni aucun critère explicatif.
          </div>
        ) : (
          <div className="brain-v2-reasons-list">
            {reasons.map((reason, index) => (
              <div key={`${reason}-${index}`} className="brain-v2-reason">
                <span className="brain-v2-reason-index">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <span className="brain-v2-reason-check" aria-hidden="true">✓</span>
                <span className="brain-v2-reason-text">{reason}</span>
              </div>
            ))}
          </div>
        )}
      </section>

      <footer className="brain-v2-footer">
        <span className="brain-v2-footer-pulse" />
        <span>Décision synchronisée avec le contrôleur</span>
      </footer>
    </article>
  );
}
