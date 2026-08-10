"use client";

import { useEffect, useMemo, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_GEOCOOLING_API_URL ?? "";

type Json = Record<string, unknown>;

type State = {
  telemetry: Json | null;
  commissioning: Json | null;
  release: Json | null;
  advisory: Json | null;
  error: string | null;
  loading: boolean;
};

async function getJson(path: string): Promise<Json> {
  const response = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return (await response.json()) as Json;
}

function bool(value: unknown) {
  return value === true;
}

function text(value: unknown, fallback = "—") {
  return typeof value === "string" && value.length ? value : fallback;
}

function num(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export default function ReadinessPage() {
  const [state, setState] = useState<State>({
    telemetry: null,
    commissioning: null,
    release: null,
    advisory: null,
    error: null,
    loading: true,
  });

  useEffect(() => {
    let active = true;

    const load = async () => {
      try {
        const [telemetry, commissioning, release, advisory] = await Promise.all([
          getJson("/geocooling/brain-v2/integration/home-assistant/telemetry-health"),
          getJson("/geocooling/brain-v2/integration/home-assistant/commissioning-readiness"),
          getJson("/geocooling/brain-v2/integration/home-assistant/release-readiness"),
          getJson("/geocooling/rc3/weather-inertia/precooling-advisory"),
        ]);
        if (active) {
          setState({ telemetry, commissioning, release, advisory, error: null, loading: false });
        }
      } catch (error) {
        if (active) {
          setState((current) => ({
            ...current,
            loading: false,
            error: error instanceof Error ? error.message : "Readiness indisponible",
          }));
        }
      }
    };

    void load();
    const timer = window.setInterval(load, 60_000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  const summary = useMemo(() => {
    const telemetryReady = bool(state.telemetry?.ready);
    const commissioningState = text(state.commissioning?.state, "UNKNOWN");
    const releaseState = text(state.release?.state, "UNKNOWN");
    const deploymentReady = bool(state.release?.deployment_ready);
    const advisorySafety = (state.advisory?.safety ?? {}) as Json;
    const shadowSafe =
      bool(advisorySafety.advisory_only) &&
      advisorySafety.controller_authorized === false &&
      advisorySafety.hardware_write === false &&
      advisorySafety.promotion_to_controller_allowed === false;

    const softwareReady = telemetryReady && shadowSafe;
    const physicalPending = commissioningState === "FIELD_CERTIFICATION_REQUIRED";

    return { telemetryReady, commissioningState, releaseState, deploymentReady, shadowSafe, softwareReady, physicalPending };
  }, [state]);

  const roleCount = num(state.telemetry?.required_role_count);
  const readyRoleCount = num(state.telemetry?.ready_required_role_count);

  return (
    <main className="page">
      <header className="hero">
        <div>
          <p className="eyebrow">GeoCooling · Finalisation</p>
          <h1>Release Readiness</h1>
          <p className="subtitle">Vue unique de l’état logiciel, de la télémétrie, du commissioning terrain et de la sécurité Shadow.</p>
        </div>
        <div className={`badge ${summary.deploymentReady ? "ready" : summary.softwareReady ? "pending" : "blocked"}`}>
          {summary.deploymentReady ? "READY FOR DEPLOYMENT" : summary.physicalPending ? "LOGICIEL PRÊT · TERRAIN REQUIS" : "À FINALISER"}
        </div>
      </header>

      {state.loading && <section className="panel">Chargement…</section>}
      {state.error && <section className="panel error">{state.error}</section>}

      {!state.loading && !state.error && (
        <>
          <section className="grid">
            <article className="card">
              <span>Télémétrie</span>
              <strong>{summary.telemetryReady ? "READY" : "BLOCKED"}</strong>
              <small>{readyRoleCount ?? "—"}/{roleCount ?? "—"} rôles requis</small>
            </article>
            <article className="card">
              <span>Commissioning</span>
              <strong>{summary.commissioningState}</strong>
              <small>EV / M11 / M13</small>
            </article>
            <article className="card">
              <span>Release</span>
              <strong>{summary.releaseState}</strong>
              <small>{summary.deploymentReady ? "déploiement autorisable" : "déploiement bloqué"}</small>
            </article>
            <article className="card">
              <span>Intelligence</span>
              <strong>{summary.shadowSafe ? "SHADOW SAFE" : "CHECK"}</strong>
              <small>{text(state.advisory?.state)}</small>
            </article>
          </section>

          <section className="panel">
            <h2>Lecture opérationnelle</h2>
            <div className="checks">
              <p className={summary.telemetryReady ? "ok" : "ko"}>● 5 rôles thermiques requis disponibles</p>
              <p className={summary.shadowSafe ? "ok" : "ko"}>● Pré-refroidissement sans accès contrôleur</p>
              <p className={summary.physicalPending ? "warn" : "ok"}>● Certification terrain {summary.physicalPending ? "encore requise" : "validée"}</p>
              <p className={summary.deploymentReady ? "ok" : "warn"}>● Release {summary.deploymentReady ? "prête" : "bloquée jusqu’au gate final"}</p>
            </div>
          </section>

          <section className="panel">
            <h2>Prochaine action</h2>
            <p>
              {summary.physicalPending
                ? "Raccorder puis certifier EV et les circulateurs M11/M13 avec le runbook terrain. Ne pas activer l’autopilot avant READY_FOR_DEPLOYMENT."
                : summary.deploymentReady
                  ? "Effectuer la revue finale de configuration puis préparer l’activation contrôlée."
                  : "Corriger les blocs rouges avant toute activation matérielle."}
            </p>
          </section>
        </>
      )}

      <style jsx>{`
        .page{min-height:100vh;padding:32px;background:#07101f;color:#f4f7fb}.hero{display:flex;justify-content:space-between;gap:24px;align-items:flex-start}.eyebrow{color:#83b8ff;text-transform:uppercase;letter-spacing:.13em;font-size:12px}h1{margin:6px 0 0;font-size:clamp(34px,5vw,58px)}h2{margin-top:0}.subtitle,small,.panel p,.card span{color:#95a5be}.subtitle{max-width:760px}.badge{padding:10px 14px;border-radius:999px;white-space:nowrap}.ready{color:#72e0b1;border:1px solid rgba(91,216,165,.35);background:rgba(30,130,91,.14)}.pending{color:#ffd08a;border:1px solid rgba(255,190,90,.35);background:rgba(180,110,20,.12)}.blocked{color:#ffb2b2;border:1px solid rgba(255,120,120,.35)}.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px;margin-top:26px}.card,.panel{border:1px solid rgba(148,170,205,.16);background:rgba(14,27,48,.78);box-shadow:0 20px 60px rgba(0,0,0,.22)}.card{padding:20px;border-radius:18px}.card strong{display:block;font-size:22px;margin:8px 0}.panel{padding:24px;border-radius:22px;margin:22px 0}.checks p{margin:9px 0}.ok{color:#72e0b1!important}.warn{color:#ffd08a!important}.ko,.error{color:#ffb2b2!important}@media(max-width:900px){.page{padding:20px}.hero{flex-direction:column}.grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:560px){.grid{grid-template-columns:1fr}.badge{white-space:normal}}
      `}</style>
    </main>
  );
}
