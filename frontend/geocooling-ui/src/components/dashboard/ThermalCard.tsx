import type { GeoCoolingSnapshot } from "@/types/geocooling";
import { Metric } from "@/components/ui/Metric";
import { Panel } from "@/components/ui/Panel";

type ThermalCardProps = {
  snapshot: GeoCoolingSnapshot | null;
};

function temperature(value: number | null | undefined): string {
  return typeof value === "number" && Number.isFinite(value)
    ? value.toFixed(1)
    : "—";
}

function percentage(value: number | null | undefined): string {
  return typeof value === "number" && Number.isFinite(value)
    ? value.toFixed(1)
    : "—";
}

export function ThermalCard({ snapshot }: ThermalCardProps) {
  return (
    <Panel
      title="Ambiance & thermique"
      subtitle="Mesures bâtiment et circuit hydraulique"
      icon="◐"
    >
      <div className="gc-metric-grid gc-metric-grid--two">
        <Metric
          label="Température intérieure"
          value={temperature(snapshot?.indoorTemperature)}
          unit="°C"
          tone={
            typeof snapshot?.indoorTemperature === "number" &&
            snapshot.indoorTemperature >= 25
              ? "warning"
              : "info"
          }
          note="Température moyenne du bâtiment"
        />

        <Metric
          label="Humidité intérieure"
          value={percentage(snapshot?.humidity)}
          unit="%"
          note="Humidité relative moyenne"
        />

        <Metric
          label="Départ plancher"
          value={temperature(snapshot?.supplyTemperature)}
          unit="°C"
          note="Sonde hydraulique"
        />

        <Metric
          label="Retour plancher"
          value={temperature(snapshot?.returnTemperature)}
          unit="°C"
          note="Sonde hydraulique"
        />
      </div>
    </Panel>
  );
}
