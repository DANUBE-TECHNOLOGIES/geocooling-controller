"use client";

import { useEffect, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_GEOCOOLING_API_URL ?? "";

type Advisory = {
  generated_at?: string;
  state?: string;
  reason?: string;
  comfort?: {
    target_temperature_c?: number;
    maximum_temperature_c?: number;
  };
  forecast?: {
    weather_degraded?: boolean;
    first_limit_crossing_horizon_minutes?: number | null;
    first_limit_crossing_at?: string | null;
    first_limit_crossing_temperature_c?: number | null;
    confidence_at_crossing?: number | null;
    minimum_confidence?: number | null;
    current_indoor_temperature_c?: number | null;
    currently_above_maximum?: boolean;
    baseline_peak_temperature_c?: number | null;
  };
  recommendation?: {
    scenario?: string | null;
    lead_minutes?: number | null;
    start_horizon_minutes?: number | null;
    start_at?: string | null;
    predicted_temperature_with_cooling_c?: number | null;
    predicted_avoided_temperature_c?: number | null;
    evaluation_horizon_minutes?: number | null;
  };
  safety?: {
    advisory_only?: boolean;
    controller_authorized?: boolean;
    controller_called?: boolean;
    hardware_write?: boolean;
    mqtt_publish?: boolean;
    database_write?: boolean;
    promotion_to_controller_allowed?: boolean;
  };
};

function fmtDate(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("fr-FR", { weekday: "short", hour: "2-digit", minute: "2-digit" });
}

function fmtMinutes(value?: number | null) {
  if (value == null) return "—";
  if (value < 60) return `${value} min`;
  const hours = Math.floor(value / 60);
  const minutes = value % 60;
  return minutes ? `${hours} h ${minutes}` : `${hours} h`;
}

function stateLabel(state?: string) {
  return {
    NO_PRECOOL_NEEDED: "Aucun pré-refroidissement nécessaire",
    PRECOOL_WINDOW_IDENTIFIED: "Fenêtre de pré-refroidissement identifiée",
    PRECOOL_NOW_ADVISORY: "Pré-refroidissement conseillé maintenant",
    COOLING_ALREADY_NEEDED_ADVISORY: "Rafraîchissement déjà nécessaire",
    LOW_CONFIDENCE: "Confiance insuffisante",
    WEATHER_DEGRADED: "Prévision météo dégradée",
  }[state ?? ""] ?? state ?? "État indisponible";
}

function scenarioLabel(value?: string | null) {
  return {
    SOFT_COOLING: "Rafraîchissement modéré",
    FULL_COOLING: "Rafraîchissement nominal",
  }[value ?? ""] ?? value ?? "—";
}

export default function PrecoolingPage() {
  const [data, setData] = useState<Advisory | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const response = await fetch(`${API_BASE}/geocooling/rc3/weather-inertia/precooling-advisory`, { cache: "no-store" });
        if (!response.ok) throw new Error(`API ${response.status}`);
        const payload = (await response.json()) as Advisory;
        if (active) { setData(payload); setError(null); }
      } catch (caught) {
        if (active) setError(caught instanceof Error ? caught.message : "Advisory indisponible");
      } finally {
        if (active) setLoading(false);
      }
    };
    void load();
    const timer = window.setInterval(load, 60_000);
    return () => { active = false; window.clearInterval(timer); };
  }, []);

  const forecast = data?.forecast ?? {};
  const recommendation = data?.recommendation ?? {};
  const safety = data?.safety ?? {};
  const confidence = forecast.confidence_at_crossing;
  const shadowSafe =
    safety.advisory_only === true &&
    safety.controller_authorized === false &&
    safety.hardware_write === false &&
    safety.promotion_to_controller_allowed === false;

  return (
    <main className="page">
      <header className="hero">
        <div>
          <p className="eyebrow">RC3 · Shadow Intelligence</p>
          <h1>Pré-refroidissement</h1>
          <p className="subtitle">Recommandation temporelle issue de la météo de Chevannes, de l’inertie thermique et des trajectoires GeoCooling.</p>
        </div>
        <div className={`badge ${shadowSafe ? "safe" : "warning"}`}>{shadowSafe ? "Shadow · aucun pilotage" : "Vérifier les invariants"}</div>
      </header>

      {loading && <section className="panel">Chargement…</section>}
      {error && <section className="panel error">Advisory indisponible : {error}</section>}

      {data && (
        <>
          <section className="decision panel">
            <div><span className="label">État</span><h2>{stateLabel(data.state)}</h2>{data.reason && <p>{data.reason}</p>}</div>
            <div className="decisionValue"><span>Démarrage conseillé</span><strong>{fmtDate(recommendation.start_at)}</strong><small>avance {fmtMinutes(recommendation.lead_minutes)}</small></div>
          </section>

          <section className="grid">
            <article className="card"><span>Température intérieure</span><strong>{forecast.current_indoor_temperature_c?.toFixed(1) ?? "—"} °C</strong><small>{forecast.currently_above_maximum ? "au-dessus du maximum" : "dans la plage"}</small></article>
            <article className="card"><span>Maximum confort</span><strong>{data.comfort?.maximum_temperature_c?.toFixed(1) ?? "—"} °C</strong><small>cible {data.comfort?.target_temperature_c?.toFixed(1) ?? "—"} °C</small></article>
            <article className="card"><span>Premier dépassement</span><strong>{fmtDate(forecast.first_limit_crossing_at)}</strong><small>{fmtMinutes(forecast.first_limit_crossing_horizon_minutes)}</small></article>
            <article className="card"><span>Confiance</span><strong>{confidence == null ? "—" : `${Math.round(confidence * 100)} %`}</strong><small>minimum {forecast.minimum_confidence == null ? "—" : `${Math.round(forecast.minimum_confidence * 100)} %`}</small></article>
          </section>

          <section className="panel">
            <div className="panelHeader"><div><span className="label">Scénario recommandé</span><h2>{scenarioLabel(recommendation.scenario)}</h2></div><div className="weatherBadge">Open-Meteo · anticipation active</div></div>
            <div className="grid compact">
              <article className="card subtle"><span>Température évaluée avec refroidissement</span><strong>{recommendation.predicted_temperature_with_cooling_c?.toFixed(1) ?? "—"} °C</strong><small>horizon {fmtMinutes(recommendation.evaluation_horizon_minutes)}</small></article>
              <article className="card subtle"><span>Échauffement évité</span><strong>{recommendation.predicted_avoided_temperature_c?.toFixed(2) ?? "—"} °C</strong><small>baseline peak {forecast.baseline_peak_temperature_c?.toFixed(1) ?? "—"} °C</small></article>
            </div>
          </section>

          <section className="panel safetyPanel">
            <div className="panelHeader"><div><span className="label">Sécurité</span><h2>Conseil uniquement</h2></div><strong className={shadowSafe ? "ok" : "ko"}>{shadowSafe ? "INVARIANTS OK" : "À CONTRÔLER"}</strong></div>
            <div className="safetyGrid">
              <span>Controller autorisé <b>{String(safety.controller_authorized)}</b></span>
              <span>Écriture hardware <b>{String(safety.hardware_write)}</b></span>
              <span>Publication MQTT <b>{String(safety.mqtt_publish)}</b></span>
              <span>Écriture base <b>{String(safety.database_write)}</b></span>
              <span>Promotion contrôleur <b>{String(safety.promotion_to_controller_allowed)}</b></span>
            </div>
          </section>
        </>
      )}

      <style jsx>{`
        .page{min-height:100vh;padding:32px;background:#07101f;color:#f4f7fb}.hero,.panelHeader{display:flex;justify-content:space-between;gap:24px;align-items:flex-start}.eyebrow,.label{color:#83b8ff;text-transform:uppercase;letter-spacing:.13em;font-size:12px}h1{margin:6px 0 0;font-size:clamp(34px,5vw,58px)}h2{margin:6px 0}.subtitle,.panel p,small,.card span{color:#95a5be}.subtitle{max-width:760px}.badge,.weatherBadge{padding:10px 14px;border-radius:999px;white-space:nowrap}.safe{color:#72e0b1;border:1px solid rgba(91,216,165,.35);background:rgba(30,130,91,.14)}.warning{color:#ffd08a;border:1px solid rgba(255,190,90,.35)}.panel,.card{border:1px solid rgba(148,170,205,.16);background:rgba(14,27,48,.78);box-shadow:0 20px 60px rgba(0,0,0,.22)}.panel{padding:24px;border-radius:22px;margin:22px 0}.error{color:#ffb2b2}.decision{display:flex;justify-content:space-between;gap:30px;align-items:center}.decisionValue{text-align:right}.decisionValue span,.decisionValue small{display:block;color:#95a5be}.decisionValue strong{display:block;font-size:30px;margin:6px 0}.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px}.compact{grid-template-columns:repeat(2,minmax(0,1fr));margin-top:20px}.card{padding:20px;border-radius:18px}.card strong{display:block;font-size:26px;margin-top:8px}.card small{display:block;margin-top:6px}.subtle{box-shadow:none}.weatherBadge{color:#9ec9ff;background:rgba(77,132,208,.14);border:1px solid rgba(115,167,235,.25)}.safetyGrid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px;margin-top:18px}.safetyGrid span{padding:12px;border-radius:12px;background:rgba(255,255,255,.035);color:#95a5be}.safetyGrid b{display:block;color:#f4f7fb;margin-top:5px}.ok{color:#72e0b1}.ko{color:#ffb2b2}@media(max-width:900px){.page{padding:20px}.hero,.decision,.panelHeader{flex-direction:column}.decisionValue{text-align:left}.grid,.safetyGrid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:560px){.grid,.compact,.safetyGrid{grid-template-columns:1fr}.badge,.weatherBadge{white-space:normal}}
      `}</style>
    </main>
  );
}
