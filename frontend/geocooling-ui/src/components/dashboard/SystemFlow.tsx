import type { GeoCoolingSnapshot } from "@/types/geocooling";

export function SystemFlow({ snapshot }: { snapshot: GeoCoolingSnapshot }) {
  const nodes = [
    ["💧", "Nappe", `${snapshot.sourceInTemperature}°C`],
    ["▧", "Échangeur", `${snapshot.sourceOutTemperature}°C`],
    ["◉", "Pompe", snapshot.pumpRunning ? "ON" : "OFF"],
  ];

  return (
    <article className="panel">
      <div className="panel-head">
        <div>
          <h2 className="panel-title">Flux hydraulique</h2>
          <div className="panel-kicker">Synoptique simplifié de l’installation</div>
        </div>
      </div>

      <div className="flow">
        {nodes.map(([icon, label, value], index) => (
          <div style={{ display: "contents" }} key={label}>
            <div className={`flow-node ${snapshot.pumpRunning ? "active" : ""}`}>
              <div className="flow-icon">{icon}</div>
              <div className="flow-label">{label}</div>
              <div className="flow-temp">{value}</div>
            </div>
            {index < nodes.length - 1 ? <div className="flow-line" /> : null}
          </div>
        ))}
      </div>
    </article>
  );
}
