"use client";

import { BrainCard } from "@/components/dashboard/BrainCard";
import { ControllerStatusCard } from "@/components/dashboard/ControllerStatusCard";
import { HydraulicCard } from "@/components/dashboard/HydraulicCard";
import { MissionHeader } from "@/components/dashboard/MissionHeader";
import { RuntimeCard } from "@/components/dashboard/RuntimeCard";
import { SystemFlow } from "@/components/dashboard/SystemFlow";
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
            <strong>
              Connexion au contrôleur GeoCooling…
            </strong>

            <span>
              Chargement du premier snapshot.
            </span>
          </div>
        </section>
      ) : null}

      {error ? (
        <section
          className="gc-error-banner"
          role="alert"
        >
          <div>
            <strong>
              Communication interrompue
            </strong>

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

      {snapshot ? (
        <>
          <section
            className="gc-command-layout"
            aria-label="Supervision principale"
          >
            <div className="gc-command-layout__scada">
              <SystemFlow snapshot={snapshot} />
            </div>

            <aside className="gc-command-layout__side">
              <BrainCard snapshot={snapshot} />

              <ControllerStatusCard
                snapshot={snapshot}
                connected={connected}
              />
            </aside>
          </section>

          <section
            className="gc-technical-section"
            aria-labelledby="gc-technical-title"
          >
            <header className="gc-section-heading">
              <div>
                <p className="gc-section-heading__eyebrow">
                  EXPLOITATION
                </p>

                <h2 id="gc-technical-title">
                  Données techniques
                </h2>
              </div>

              <span className="gc-section-heading__status">
                Mise à jour automatique toutes les 5 secondes
              </span>
            </header>

            <div className="gc-technical-grid">
              <ThermalCard snapshot={snapshot} />

              <HydraulicCard snapshot={snapshot} />

              <RuntimeCard
                snapshot={snapshot}
                lastUpdate={lastUpdate}
              />
            </div>
          </section>
        </>
      ) : null}
    </AppShell>
  );
}
