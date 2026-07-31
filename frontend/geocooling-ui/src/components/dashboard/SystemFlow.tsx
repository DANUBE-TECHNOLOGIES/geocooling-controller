import type { GeoCoolingSnapshot } from "@/types/geocooling";

function temp(v: number | null) {
  return v === null ? "--.- °C" : `${v.toFixed(1)} °C`;
}

function State({
  label,
  value,
}: {
  label: string;
  value: boolean;
}) {
  return (
    <div className="flow-state">
      <span>{label}</span>

      <span
        className={
          value
            ? "flow-state-on"
            : "flow-state-off"
        }
      >
        {value ? "ON" : "OFF"}
      </span>
    </div>
  );
}

export function SystemFlow({
  snapshot,
}: {
  snapshot: GeoCoolingSnapshot;
}) {
  return (
    <article className="panel">

      <div className="panel-head">

        <div>

          <h2 className="panel-title">
            Synoptique hydraulique
          </h2>

          <div className="panel-kicker">
            Circuit de refroidissement
          </div>

        </div>

      </div>

      <div className="hydraulic-flow">

        <div className="equipment">

          <div className="equipment-title">
            💧 NAPPE
          </div>

          <div className="equipment-value">
            {temp(snapshot.sourceInTemperature)}
          </div>

        </div>

        <div className="flow-arrow">
          ➜
        </div>

        <div className="equipment">

          <div className="equipment-title">
            ♨ ÉCHANGEUR
          </div>

          <div className="equipment-value">
            {temp(snapshot.sourceOutTemperature)}
          </div>

        </div>

        <div className="flow-arrow">
          ➜
        </div>

        <div className="equipment">

          <div className="equipment-title">
            ⚙ POMPE
          </div>

          <div className="equipment-value">
            {snapshot.pumpRunning ? "EN SERVICE" : "ARRÊT"}
          </div>

        </div>

        <div className="flow-arrow">
          ➜
        </div>

        <div className="equipment">

          <div className="equipment-title">
            🏠 PLANCHER
          </div>

          <div className="equipment-value">
            {temp(snapshot.supplyTemperature)}
          </div>

        </div>

      </div>

      <div className="flow-states">

        <State
          label="Pompe"
          value={snapshot.pumpRunning}
        />

        <State
          label="Vanne"
          value={snapshot.valveOpen}
        />

        <State
          label="Sécurité"
          value={snapshot.safetyOk}
        />

      </div>

      <div className="flow-temps">

        <div>
          <strong>Départ</strong>
          <br />
          {temp(snapshot.supplyTemperature)}
        </div>

        <div>
          <strong>Retour</strong>
          <br />
          {temp(snapshot.returnTemperature)}
        </div>

        <div>
          <strong>Source</strong>
          <br />
          {temp(snapshot.sourceInTemperature)}
        </div>

        <div>
          <strong>Rejet</strong>
          <br />
          {temp(snapshot.sourceOutTemperature)}
        </div>

      </div>

    </article>
  );
}
