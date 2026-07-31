"use client";

import { BrainCard } from "@/components/dashboard/BrainCard";
import { ControllerStatusCard } from "@/components/dashboard/ControllerStatusCard";
import { HydraulicCard } from "@/components/dashboard/HydraulicCard";
import { RuntimeCard } from "@/components/dashboard/RuntimeCard";
import { ThermalCard } from "@/components/dashboard/ThermalCard";
import { AppShell } from "@/components/layout/AppShell";
import { StatusBadge } from "@/components/ui/StatusBadge";
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
      <section className="gc-hero">
        <div>
          <p className="gc-hero__eyebrow">
            SUPERVISION TEMPS RÉEL
          </p>

          <h2 className="gc-hero__title">
            Pilotage intelligent du rafraîchissement géothermique
          </h2>

          <p className="gc-hero__description">
            Surveillance du bâtiment, du circuit hydraulique et des décisions
            du moteur GeoCooling Brain.
          </p>
        </div>

        <div className="gc-hero__badges">
          <StatusBadge
            label={snapshot?.pumpRunning ? "POMPE ACTIVE" : "POMPE ARRÊTÉE"}
            tone={snapshot?.pumpRunning ? "success" : "neutral"}
            pulse={snapshot?.pumpRunning === true}
          />

          <StatusBadge
            label={snapshot?.valveOpen ? "VANNE OUVERTE" : "VANNE FERMÉE"}
            tone={snapshot?.valveOpen ? "success" : "neutral"}
          />

          <StatusBadge
            label={
              snapshot?.safetySafe === true
                ? "SÉCURITÉ OK"
                : snapshot?.safetySafe === false
                  ? "ALERTE SÉCURITÉ"
                  : "SÉCURITÉ INCONNUE"
            }
            tone={
              snapshot?.safetySafe === true
                ? "success"
                : snapshot?.safetySafe === false
                  ? "danger"
                  : "neutral"
            }
          />
        </div>
      </section>

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
