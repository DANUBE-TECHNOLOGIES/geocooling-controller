import type { GeoCoolingSnapshot } from "@/types/geocooling";
import { Metric } from "@/components/ui/Metric";
import { Panel } from "@/components/ui/Panel";
import { StatusBadge } from "@/components/ui/StatusBadge";

type HydraulicCardProps = {
  snapshot: GeoCoolingSnapshot | null;
};

function temperature(value: number | null | undefined): string {
  return typeof value === "number" && Number.isFinite(value)
    ? value.toFixed(1)
    : "—";
}

export function HydraulicCard({ snapshot }: HydraulicCardProps) {
  const running = snapshot?.pumpRunning === true;
  const valveOpen = snapshot?.valveOpen === true;

  return (
    <Panel
      title="Circuit hydraulique"
      subtitle="Source froide, vanne et circulateur"
      icon="≈"
      action={
        <StatusBadge
          label={running ? "CIRCULATION ACTIVE" : "CIRCULATION ARRÊTÉE"}
          tone={running ? "success" : "neutral"}
          pulse={running}
        />
      }
    >
      <div className="gc-hydraulic-flow">
        <div className="gc-flow-node">
          <span className="gc-flow-node__icon">◉</span>
          <span>Forage</span>
          <strong>{temperature(snapshot?.sourceInTemperature)} °C</strong>
        </div>

        <div className={`gc-flow-line ${valveOpen ? "is-active" : ""}`}>
          <span />
          <span />
          <span />
        </div>

        <div className={`gc-flow-device ${valveOpen ? "is-active" : ""}`}>
          <span>VANNE</span>
          <strong>{valveOpen ? "OUVERTE" : "FERMÉE"}</strong>
        </div>

        <div className={`gc-flow-line ${running ? "is-active" : ""}`}>
          <span />
          <span />
          <span />
        </div>

        <div className={`gc-flow-device gc-flow-device--pump ${running ? "is-active" : ""}`}>
          <span className={running ? "gc-pump-symbol is-spinning" : "gc-pump-symbol"}>
            ⟳
          </span>
          <strong>{running ? "POMPE ON" : "POMPE OFF"}</strong>
        </div>

        <div className={`gc-flow-line ${running ? "is-active" : ""}`}>
          <span />
          <span />
          <span />
        </div>

        <div className="gc-flow-node">
          <span className="gc-flow-node__icon">▦</span>
          <span>Plancher</span>
          <strong>{temperature(snapshot?.supplyTemperature)} °C</strong>
        </div>
      </div>

      <div className="gc-metric-grid gc-metric-grid--two">
        <Metric
          label="Arrivée forage"
          value={temperature(snapshot?.sourceInTemperature)}
          unit="°C"
          note="Température source disponible"
        />

        <Metric
          label="Retour forage"
          value={temperature(snapshot?.sourceOutTemperature)}
          unit="°C"
          note="Température après échange"
        />
      </div>
    </Panel>
  );
}
