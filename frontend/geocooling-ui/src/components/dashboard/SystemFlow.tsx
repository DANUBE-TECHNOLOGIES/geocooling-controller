import type { GeoCoolingSnapshot } from "@/types/geocooling";

import {
  EquipmentCard,
  FlowArrow,
  FlowState,
  TemperatureBadge,
} from "./system";

function temp(value: number | null): string {
  return value === null
    ? "--.- °C"
    : `${value.toFixed(1)} °C`;
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

        <EquipmentCard
          title="💧 NAPPE"
          value={temp(snapshot.sourceInTemperature)}
        />

        <FlowArrow />

        <EquipmentCard
          title="♨ ÉCHANGEUR"
          value={temp(snapshot.sourceOutTemperature)}
        />

        <FlowArrow />

        <EquipmentCard
          title="⚙ POMPE"
          value={
            snapshot.pumpRunning
              ? "EN SERVICE"
              : "ARRÊT"
          }
        />

        <FlowArrow />

        <EquipmentCard
          title="🏠 PLANCHER"
          value={temp(snapshot.supplyTemperature)}
        />

      </div>

      <div className="flow-states">

        <FlowState
          label="Pompe"
          value={snapshot.pumpRunning}
        />

        <FlowState
          label="Vanne"
          value={snapshot.valveOpen}
        />

        <FlowState
          label="Sécurité"
          value={snapshot.safetySafe}
          activeLabel="OK"
          inactiveLabel="ALARME"
        />

      </div>

      <div className="flow-temps">

        <TemperatureBadge
          label="Départ"
          value={snapshot.supplyTemperature}
        />

        <TemperatureBadge
          label="Retour"
          value={snapshot.returnTemperature}
        />

        <TemperatureBadge
          label="Source"
          value={snapshot.sourceInTemperature}
        />

        <TemperatureBadge
          label="Rejet"
          value={snapshot.sourceOutTemperature}
        />

      </div>

    </article>
  );
}
