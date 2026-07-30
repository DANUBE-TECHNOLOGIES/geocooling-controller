import type { GeoCoolingSnapshot } from "@/types/geocooling";
import { MetricCard } from "./MetricCard";

function format(v: number | null): string {
  return v === null ? "--" : v.toFixed(1);
}

export function OverviewGrid({
  snapshot,
}: {
  snapshot: GeoCoolingSnapshot;
}) {
  const delta =
    snapshot.returnTemperature !== null &&
    snapshot.supplyTemperature !== null
      ? (
          snapshot.returnTemperature -
          snapshot.supplyTemperature
        ).toFixed(1)
      : "--";

  return (
    <section className="overview-grid">

      <MetricCard
        icon="🏠"
        label="Maison"
        value={format(snapshot.indoorTemperature)}
        unit="°C"
        foot="Température intérieure"
        trend="Confort"
      />

      <MetricCard
        icon="💧"
        label="Humidité"
        value={format(snapshot.humidity)}
        unit="%"
        foot="Humidité relative"
        trend="Ambiance"
      />

      <MetricCard
        icon="🌍"
        label="Source"
        value={format(snapshot.sourceInTemperature)}
        unit="°C"
        foot="Nappe géothermique"
        trend="Source"
      />

      <MetricCard
        icon="❄️"
        label="Départ"
        value={format(snapshot.supplyTemperature)}
        unit="°C"
        foot="Circuit plancher"
        trend="Hydraulique"
      />

      <MetricCard
        icon="♻️"
        label="ΔT"
        value={delta}
        unit="°C"
        foot="Retour - Départ"
        trend="Performance"
        state="warning"
      />

      <MetricCard
        icon="⚙️"
        label="Pompe"
        value={snapshot.pumpRunning ? "ACTIVE" : "STOP"}
        foot={
          snapshot.pumpRunning
            ? "Circulation active"
            : "Arrêt"
        }
        trend="Hydraulique"
        state={
          snapshot.pumpRunning
            ? "on"
            : "off"
        }
      />

      <MetricCard
        icon="🚰"
        label="Vanne"
        value={
          snapshot.valveOpen
            ? "OUVERTE"
            : "FERMÉE"
        }
        foot="Circuit primaire"
        trend="Commande"
        state={
          snapshot.valveOpen
            ? "on"
            : "off"
        }
      />

      <MetricCard
        icon="🧠"
        label="Brain"
        value={snapshot.decision.summary}
        foot={snapshot.decision.reasons.join(" • ")}
        trend={`${Math.round(snapshot.decision.confidence)} %`}
        state="warning"
      />

    </section>
  );
}
