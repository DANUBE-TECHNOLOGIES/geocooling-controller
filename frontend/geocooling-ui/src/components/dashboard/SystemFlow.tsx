import type { GeoCoolingSnapshot } from "@/types/geocooling";

import {
  FlowState,
  TemperatureBadge,
} from "./system";

import ScadaHydraulicDiagram from "./system/ScadaHydraulicDiagram";

export function SystemFlow({
  snapshot,
}: {
  snapshot: GeoCoolingSnapshot;
}) {
  const circuitActive =
    snapshot.pumpRunning &&
    snapshot.valveOpen &&
    snapshot.safetySafe !== false;

  return (
    <article className="panel system-flow-panel">

      <div className="panel-head">

        <div>

          <h2 className="panel-title">
            Synoptique hydraulique
          </h2>

          <div className="panel-kicker">
            Supervision temps réel du circuit GeoCooling
          </div>

        </div>

        <div
          className={
            circuitActive
              ? "system-flow-status system-flow-status-active"
              : "system-flow-status system-flow-status-idle"
          }
        >
          <span className="system-flow-status-dot" />

          {circuitActive
            ? "CIRCUIT ACTIF"
            : "CIRCUIT À L’ARRÊT"}
        </div>

      </div>

      <ScadaHydraulicDiagram
        snapshot={snapshot}
      />

      <div className="flow-states">

        <FlowState
          label="Pompe"
          value={snapshot.pumpRunning}
          activeLabel="MARCHE"
          inactiveLabel="ARRÊT"
        />

        <FlowState
          label="Vanne"
          value={snapshot.valveOpen}
          activeLabel="OUVERTE"
          inactiveLabel="FERMÉE"
        />

        <FlowState
          label="Sécurité"
          value={snapshot.safetySafe}
          activeLabel="OK"
          inactiveLabel="ALARME"
          unknownLabel="INCONNUE"
        />

        <FlowState
          label="Contrôleur"
          value={snapshot.deviceReady}
          activeLabel="PRÊT"
          inactiveLabel="NON PRÊT"
          unknownLabel="INCONNU"
        />

      </div>

      <div className="flow-temps">

        <TemperatureBadge
          label="Entrée source"
          value={snapshot.sourceInTemperature}
        />

        <TemperatureBadge
          label="Sortie source"
          value={snapshot.sourceOutTemperature}
        />

        <TemperatureBadge
          label="Départ plancher"
          value={snapshot.supplyTemperature}
        />

        <TemperatureBadge
          label="Retour plancher"
          value={snapshot.returnTemperature}
        />

      </div>

    </article>
  );
}
