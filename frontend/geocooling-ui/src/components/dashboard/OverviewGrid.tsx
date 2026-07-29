import type { GeoCoolingSnapshot } from "@/types/geocooling";
import { MetricCard } from "./MetricCard";

export function OverviewGrid({ snapshot }: { snapshot: GeoCoolingSnapshot }) {
  return (
    <section className="overview-grid" aria-label="Indicateurs principaux">
      <MetricCard label="Maison" value={snapshot.indoorTemperature} unit="°C" foot="Température intérieure" />
      <MetricCard label="Humidité" value={snapshot.humidity} unit="%" foot="Confort hygrométrique" />
      <MetricCard label="Source" value={snapshot.sourceInTemperature} unit="°C" foot="Entrée nappe" />
      <MetricCard label="Départ" value={snapshot.supplyTemperature} unit="°C" foot="Circuit plancher" />
      <MetricCard label="Pompe" value={snapshot.pumpRunning ? "ON" : "OFF"} foot={snapshot.pumpRunning ? "Circulation active" : "À l’arrêt"} state={snapshot.pumpRunning ? "on" : "off"} />
      <MetricCard label="Électrovanne" value={snapshot.valveOpen ? "OUVERTE" : "FERMÉE"} foot="Commande hydraulique" state={snapshot.valveOpen ? "on" : "off"} />
    </section>
  );
}
