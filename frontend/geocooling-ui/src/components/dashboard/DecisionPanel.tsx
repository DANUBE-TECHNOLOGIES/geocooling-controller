import type { BrainDecision } from "@/types/geocooling";

function confidenceColor(value: number) {
  if (value >= 85) return "#27c93f";
  if (value >= 65) return "#ffbd2e";
  return "#ff5f56";
}

export function DecisionPanel({
  decision,
}: {
  decision: BrainDecision;
}) {
  const confidence = Math.max(
    0,
    Math.min(100, Math.round(decision.confidence)),
  );

  return (
    <article className="panel brain-panel">

      <header className="brain-header">

        <div>

          <div className="brain-kicker">
            INTELLIGENCE ARTIFICIELLE
          </div>

          <h2 className="brain-title">
            GeoCooling Brain
          </h2>

        </div>

        <div
          className="brain-confidence"
          style={{
            borderColor: confidenceColor(confidence),
          }}
        >
          <span
            className="brain-confidence-value"
            style={{
              color: confidenceColor(confidence),
            }}
          >
            {confidence}
          </span>

          <span className="brain-confidence-unit">
            %
          </span>
        </div>

      </header>

      <section className="brain-summary">

        <div className="brain-summary-title">
          Décision courante
        </div>

        <div className="brain-summary-text">
          {decision.summary}
        </div>

      </section>

      <section className="brain-reasons">

        <div className="brain-summary-title">
          Critères utilisés
        </div>

        {decision.reasons.length === 0 ? (
          <div className="brain-empty">
            Aucun critère fourni.
          </div>
        ) : (
          decision.reasons.map((reason, index) => (
            <div
              key={index}
              className="brain-reason"
            >
              <span className="brain-bullet">
                ✓
              </span>

              <span>
                {reason}
              </span>

            </div>
          ))
        )}

      </section>

    </article>
  );
}
