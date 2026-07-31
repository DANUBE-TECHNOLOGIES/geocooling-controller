import type { GeoCoolingSnapshot } from "@/types/geocooling";
import { MetricCard } from "./MetricCard";

function display(value: number | null): number | string {
  return value === null ? "—" : value;
}

export function OverviewGrid({ snapshot }: { snapshot: GeoCoolingSnapshot }) {
  return (
    <section className="overview-grid" aria-label="Indicateurs principaux">
      <MetricCard label="Maison" value={display(snapshot.indoorTemperature)} unit={snapshot.indoorTemperature === null ? undefined : "°C"} foot="Température intérieure" state={snapshot.indoorTemperature === null ? "warning" : "on"} />
      <MetricCard label="Humidité" value={display(snapshot.humidity)} unit={snapshot.humidity === null ? undefined : "%"} foot="Confort hygrométrique" state={snapshot.humidity === null ? "warning" : "on"} />
      <MetricCard label="Source" value={display(snapshot.sourceInTemperature)} unit={snapshot.sourceInTemperature === null ? undefined : "°C"} foot="Entrée nappe" state={snapshot.sourceInTemperature === null ? "warning" : "on"} />
      <MetricCard label="Départ" value={display(snapshot.supplyTemperature)} unit={snapshot.supplyTemperature === null ? undefined : "°C"} foot="Circuit plancher" state={snapshot.supplyTemperature === null ? "warning" : "on"} />
      <MetricCard label="Pompe" value={snapshot.pumpRunning ? "ON" : "OFF"} foot={snapshot.pumpRunning ? "Circulation active" : "À l’arrêt"} state={snapshot.pumpRunning ? "on" : "off"} />
      <MetricCard label="Électrovanne" value={snapshot.valveOpen ? "OUVERTE" : "FERMÉE"} foot="Commande hydraulique" state={snapshot.valveOpen ? "on" : "off"} />
    </section>
  );
}
