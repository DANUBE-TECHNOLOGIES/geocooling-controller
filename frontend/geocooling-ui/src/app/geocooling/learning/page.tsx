"use client";

import { useEffect, useState } from "react";

type Report = {
  status: {
    prediction_snapshots: number;
    validation_matches: number;
    calibration_samples: number;
    validation_ready: boolean;
    calibration_ready: boolean;
  };
  validation: {
    metrics: {
      mae_c?: number | null;
      rmse_c?: number | null;
      bias_c?: number | null;
    };
  };
  calibration: {
    status: string;
    current_model: Record<string, number>;
    proposal: Record<string, number>;
  };
  activation: {
    automatic: boolean;
    requires_review: boolean;
    controller_authorized: boolean;
  };
};

const API_BASE =
  process.env.NEXT_PUBLIC_GEOCOOLING_API_URL ?? "";

const labels: Record<string, string> = {
  fast_time_constant_hours: "Inertie rapide",
  slow_time_constant_hours: "Inertie lente",
  mass_coupling: "Couplage masse",
  solar_gain_c_per_hour_at_full_sun: "Gain solaire",
  soft_cooling_c_per_hour: "Efficacité modérée",
  full_cooling_c_per_hour: "Efficacité nominale",
  model_confidence: "Confiance modèle",
};

export default function LearningPage() {
  const [data, setData] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const response = await fetch(
          `${API_BASE}/geocooling/rc3/learning/report`,
          { cache: "no-store" },
        );

        if (!response.ok) {
          throw new Error(`API ${response.status}`);
        }

        setData((await response.json()) as Report);
        setError(null);
      } catch (caught) {
        setError(
          caught instanceof Error
            ? caught.message
            : "Rapport indisponible",
        );
      }
    };

    void load();
    const timer = window.setInterval(load, 60_000);

    return () => window.clearInterval(timer);
  }, []);

  return (
    <main className="page">
      <header>
        <div>
          <p className="eyebrow">RC3.8 · Boucle d’apprentissage</p>
          <h1>Validation vers calibration</h1>
          <p className="subtitle">
            Les erreurs réellement mesurées alimentent directement
            une proposition de calibration.
          </p>
        </div>
        <span className="badge">
          Validation humaine obligatoire
        </span>
      </header>

      {error && <section className="panel error">{error}</section>}
      {!data && !error && (
        <section className="panel">Chargement…</section>
      )}

      {data && (
        <>
          <section className="metrics">
            <article>
              <span>Captures</span>
              <strong>{data.status.prediction_snapshots}</strong>
            </article>
            <article>
              <span>Correspondances</span>
              <strong>{data.status.validation_matches}</strong>
            </article>
            <article>
              <span>Échantillons</span>
              <strong>{data.status.calibration_samples}</strong>
            </article>
            <article>
              <span>Statut</span>
              <strong>
                {data.status.calibration_ready
                  ? "Proposition prête"
                  : "Apprentissage"}
              </strong>
            </article>
          </section>

          <section className="panel">
            <h2>Chaîne d’apprentissage</h2>
            <div className="pipeline">
              <span>Prévision</span><i>→</i>
              <span>Mesure réelle</span><i>→</i>
              <span>Erreur</span><i>→</i>
              <span>Calibration proposée</span>
            </div>
          </section>

          <section className="panel">
            <h2>Précision observée</h2>
            <div className="precision">
              <div><span>MAE</span><strong>
                {data.validation.metrics.mae_c != null
                  ? `${data.validation.metrics.mae_c.toFixed(2)}°C`
                  : "—"}
              </strong></div>
              <div><span>RMSE</span><strong>
                {data.validation.metrics.rmse_c != null
                  ? `${data.validation.metrics.rmse_c.toFixed(2)}°C`
                  : "—"}
              </strong></div>
              <div><span>Biais</span><strong>
                {data.validation.metrics.bias_c != null
                  ? `${data.validation.metrics.bias_c.toFixed(2)}°C`
                  : "—"}
              </strong></div>
            </div>
          </section>

          <section className="panel">
            <h2>Paramètres actuels et proposés</h2>
            <div className="table">
              <div className="row headerRow">
                <span>Paramètre</span>
                <span>Actuel</span>
                <span>Proposé</span>
                <span>Écart</span>
              </div>
              {Object.keys(labels).map((key) => {
                const current = data.calibration.current_model[key];
                const proposed = data.calibration.proposal[key];
                const delta =
                  current != null && proposed != null
                    ? proposed - current
                    : null;

                return (
                  <div className="row" key={key}>
                    <strong>{labels[key]}</strong>
                    <span>{current != null ? current.toFixed(4) : "—"}</span>
                    <span>{proposed != null ? proposed.toFixed(4) : "—"}</span>
                    <span>
                      {delta != null
                        ? `${delta >= 0 ? "+" : ""}${delta.toFixed(4)}`
                        : "—"}
                    </span>
                  </div>
                );
              })}
            </div>
          </section>
        </>
      )}

      <style jsx>{`
        .page{min-height:100vh;padding:32px;color:#f4f7fb;background:#07101f}
        header{display:flex;justify-content:space-between;gap:24px}
        .eyebrow{color:#72e0b1;letter-spacing:.14em;text-transform:uppercase;font-size:12px}
        h1{font-size:clamp(32px,5vw,56px);margin:6px 0 12px}
        .subtitle{color:#9eacc3;max-width:720px}
        .badge{padding:10px 14px;border:1px solid rgba(114,224,177,.35);border-radius:999px;color:#72e0b1;height:max-content}
        .metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin:28px 0 20px}
        .metrics article,.panel{border:1px solid rgba(148,170,205,.16);background:rgba(14,27,48,.78);border-radius:20px}
        .metrics article{padding:20px}.metrics span,.precision span{color:#91a2bd}.metrics strong{display:block;margin-top:8px;font-size:24px}
        .panel{padding:24px;margin-bottom:20px}
        .pipeline{display:flex;gap:14px;align-items:center;flex-wrap:wrap;margin-top:18px}
        .pipeline span{padding:12px 16px;border-radius:14px;background:rgba(115,141,181,.12)}.pipeline i{color:#72e0b1}
        .precision{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-top:18px}
        .precision div{padding:16px;border-radius:14px;background:rgba(115,141,181,.1)}.precision strong{display:block;font-size:24px}
        .row{display:grid;grid-template-columns:2fr 1fr 1fr 1fr;gap:18px;padding:13px 0;border-top:1px solid rgba(148,170,205,.1)}
        .headerRow{color:#91a2bd;border-top:0}.error{color:#ffb2b2}
        @media(max-width:850px){.page{padding:20px}header{flex-direction:column}.metrics{grid-template-columns:repeat(2,1fr)}.table{overflow:auto}.row{min-width:700px}}
      `}</style>
    </main>
  );
}
