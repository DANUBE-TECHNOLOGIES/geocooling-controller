"use client";

import { DecisionPanel } from "@/components/dashboard/DecisionPanel";
import { OverviewGrid } from "@/components/dashboard/OverviewGrid";
import { SystemFlow } from "@/components/dashboard/SystemFlow";
import { AppShell } from "@/components/layout/AppShell";
import { useGeoCooling } from "@/hooks/useGeoCooling";

function formatUpdate(date: Date | null): string {
  if (!date) return "En attente";
  return date.toLocaleTimeString("fr-FR", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export default function Home() {
  const { snapshot, loading, refreshing, error, lastUpdate, refresh } = useGeoCooling();
  const connected = Boolean(snapshot && !error);

  return (
    <AppShell connected={connected} mode={snapshot?.mode}>
      <section className="page-heading">
        <div>
          <p className="eyebrow">Vue d’ensemble</p>
          <h1>Supervision GeoCooling</h1>
          <p className="page-copy">
            État thermique, hydraulique et décisionnel de l’installation.
          </p>
        </div>
        <button
          className={`live-pill live-button ${error ? "live-error" : ""}`}
          type="button"
          onClick={() => void refresh(false)}
          disabled={refreshing}
          title="Actualiser maintenant"
        >
          <span className="live-dot" />
          {refreshing ? "Actualisation…" : `Dernière mise à jour : ${formatUpdate(lastUpdate)}`}
        </button>
      </section>

      {loading && !snapshot ? (
        <section className="state-panel" aria-live="polite">
          <div className="state-spinner" />
          <div>
            <h2>Connexion au contrôleur…</h2>
            <p>Lecture des données temps réel GeoCooling.</p>
          </div>
        </section>
      ) : null}

      {error ? (
        <section className="state-panel state-error" role="alert">
          <div>
            <h2>Backend GeoCooling indisponible</h2>
            <p>{error}</p>
          </div>
          <button type="button" onClick={() => void refresh(false)}>Réessayer</button>
        </section>
      ) : null}

      {snapshot ? (
        <>
          <OverviewGrid snapshot={snapshot} />
          <section className="dashboard-columns">
            <DecisionPanel decision={snapshot.decision} />
            <SystemFlow snapshot={snapshot} />
          </section>
        </>
      ) : null}
    </AppShell>
  );
}
