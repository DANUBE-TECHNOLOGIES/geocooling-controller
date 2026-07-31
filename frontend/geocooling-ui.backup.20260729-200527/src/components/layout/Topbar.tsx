import type { GeoCoolingMode } from "@/types/geocooling";

type TopbarProps = {
  connected?: boolean;
  mode?: GeoCoolingMode;
};

const modeLabels: Record<GeoCoolingMode, string> = {
  simulation: "Simulation",
  automatic: "Automatique",
  manual: "Manuel",
  unknown: "Inconnu",
};

export function Topbar({ connected = false, mode = "unknown" }: TopbarProps) {
  return (
    <header className="topbar">
      <div className="topbar-left">
        <span>⌂</span>
        <span>Installation principale</span>
      </div>
      <div className="topbar-right">
        <div className={`status-chip ${connected ? "connected" : "disconnected"}`}>
          Backend <strong>{connected ? "Connecté" : "Déconnecté"}</strong>
        </div>
        <div className="status-chip">Mode <strong>{modeLabels[mode]}</strong></div>
      </div>
    </header>
  );
}
