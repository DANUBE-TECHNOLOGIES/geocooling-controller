import type { BrainDecision } from "@/types/geocooling";

export function DecisionPanel({ decision }: { decision: BrainDecision }) {
  return (
    <article className="panel">
      <div className="panel-head">
        <div>
          <h2 className="panel-title">Décision du Brain</h2>
          <div className="panel-kicker">Analyse explicable en temps réel</div>
        </div>
        <div className="confidence">{decision.confidence}%</div>
      </div>

      <div className="decision-main">{decision.summary}</div>
      <div className="reason-list">
        {decision.reasons.map((reason) => <div className="reason" key={reason}>{reason}</div>)}
      </div>
    </article>
  );
}
