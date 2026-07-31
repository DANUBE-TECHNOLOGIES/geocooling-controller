"use client";

import { BrainCard } from "@/components/dashboard/BrainCard";
import { ControllerStatusCard } from "@/components/dashboard/ControllerStatusCard";
import { HydraulicCard } from "@/components/dashboard/HydraulicCard";
import { MissionHeader } from "@/components/dashboard/MissionHeader";
import { RuntimeCard } from "@/components/dashboard/RuntimeCard";
import { ThermalCard } from "@/components/dashboard/ThermalCard";
import { AppShell } from "@/components/layout/AppShell";
import { useGeoCooling } from "@/hooks/useGeoCooling";

export default function Home() {
  const {
    snapshot,
    loading,
    refreshing,
    error,
    lastUpdate,
    responseTime,
    refresh,
  } = useGeoCooling();

  const connected = Boolean(snapshot && !error);
  const mode = String(snapshot?.mode ?? "INCONNU");

  return (
    <AppShell
      connected={connected}
      mode={mode}
      refreshing={refreshing}
      lastUpdate={lastUpdate}
      generatedAt={snapshot?.generatedAt}
      responseTime={responseTime}
      onRefresh={() => {
        void refresh();
      }}
    >
      <MissionHeader
        snapshot={snapshot}
        connected={connected}
      />

      {loading && !snapshot ? (
        <section className="gc-loading-state">
          <div className="gc-loading-spinner" />
          <div>
            <strong>Connexion au contrôleur GeoCooling…</strong>
            <span>Chargement du premier snapshot.</span>
          </div>
        </section>
      ) : null}

      {error ? (
        <section className="gc-error-banner" role="alert">
          <div>
            <strong>Communication interrompue</strong>
            <p>{error}</p>
          </div>

          <button
            type="button"
            onClick={() => {
              void refresh();
            }}
          >
            Réessayer
          </button>
        </section>
      ) : null}

      <div className="gc-dashboard-grid">
        <ControllerStatusCard
          snapshot={snapshot}
          connected={connected}
        />

        <ThermalCard snapshot={snapshot} />

        <HydraulicCard snapshot={snapshot} />

        <BrainCard snapshot={snapshot} />

        <RuntimeCard
          snapshot={snapshot}
          lastUpdate={lastUpdate}
        />
      </div>
    </AppShell>
  );
}
