"use client";

import { DecisionPanel } from "@/components/dashboard/DecisionPanel";
import { OverviewGrid } from "@/components/dashboard/OverviewGrid";
import { SystemFlow } from "@/components/dashboard/SystemFlow";
import { AppShell } from "@/components/layout/AppShell";
import { useGeoCooling } from "@/hooks/useGeoCooling";

function formatUpdate(date: Date | null): string {
  if (!date) return "--:--:--";

  return date.toLocaleTimeString("fr-FR", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export default function Home() {

  const {
    snapshot,
    loading,
    refreshing,
    error,
    lastUpdate,
    refresh,
  } = useGeoCooling();

  const connected = Boolean(snapshot && !error);

  return (
    <AppShell
      connected={connected}
      mode={snapshot?.mode}
    >

      <section className="dashboard-header">

        <div>

          <div className="dashboard-tag">
            SUPERVISION TEMPS RÉEL
          </div>

          <h1 className="dashboard-title">
            GeoCooling Enterprise
          </h1>

          <div className="dashboard-subtitle">
            Pilotage intelligent du bâtiment
          </div>

        </div>

        <div className="dashboard-actions">

          <button
            className="live-pill live-button"
            onClick={() => void refresh(false)}
            disabled={refreshing}
          >

            {refreshing
              ? "Synchronisation..."
              : `Dernière MAJ : ${formatUpdate(lastUpdate)}`}

          </button>

        </div>

      </section>

      {loading && !snapshot && (

        <section className="state-panel">

          <div className="state-spinner" />

          <div>

            <h2>
              Connexion au contrôleur...
            </h2>

            <p>
              Chargement des données GeoCooling.
            </p>

          </div>

        </section>

      )}

      {error && (

        <section
          className="state-panel state-error"
        >

          <div>

            <h2>
              Backend indisponible
            </h2>

            <p>
              {error}
            </p>

          </div>

          <button
            onClick={() => void refresh(false)}
          >
            Réessayer
          </button>

        </section>

      )}

      {snapshot && (

        <>

          <OverviewGrid
            snapshot={snapshot}
          />

          <section
            className="enterprise-grid"
          >

            <DecisionPanel
              decision={snapshot.decision}
            />

            <SystemFlow
              snapshot={snapshot}
            />

          </section>

        </>

      )}

    </AppShell>

  );

}
