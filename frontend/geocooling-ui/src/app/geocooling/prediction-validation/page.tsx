"use client";

import { useEffect, useMemo, useState } from "react";

type HorizonMetric = {
  sample_count: number;
  mae_c: number;
  rmse_c: number;
  bias_c: number;
};

type Report = {
  generated_at: string;
  match_count: number;
  metrics: {
    mae_c: number | null;
    rmse_c: number | null;
    bias_c: number | null;
  };
  by_horizon: Record<string, HorizonMetric>;
  readiness: {
    minimum_matches: number;
    enough_data: boolean;
  };
};

const API_BASE =
  process.env.NEXT_PUBLIC_GEOCOOLING_API_URL ?? "";

function horizonLabel(minutes: string): string {
  const value = Number(minutes);

  if (value < 60) return `${value} min`;
  if (value < 1440) return `${value / 60} h`;
  return `${value / 1440} j`;
}

export default function PredictionValidationPage() {
  const [data, setData] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const response = await fetch(
          `${API_BASE}/geocooling/rc3/prediction-validation/report`,
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

  const rows = useMemo(
    () =>
      data
        ? Object.entries(data.by_horizon).sort(
            ([left], [right]) => Number(left) - Number(right),
          )
        : [],
    [data],
  );

  return (
    <main className="page">
      <header>
        <div>
          <p className="eyebrow">RC3.7 · Validation prédictive</p>
          <h1>Prévisions face aux mesures réelles</h1>
          <p className="subtitle">
            Le système compare automatiquement chaque prédiction aux
            températures observées plus tard.
          </p>
        </div>
        <span className="badge">Mode Shadow</span>
      </header>

      {error && <section className="panel error">{error}</section>}

      {!data && !error && (
        <section className="panel">Chargement du rapport…</section>
      )}

      {data && (
        <>
          <section className="metrics">
            <article>
              <span>Correspondances</span>
              <strong>{data.match_count}</strong>
            </article>
            <article>
              <span>MAE globale</span>
              <strong>
                {data.metrics.mae_c !== null
                  ? `${data.metrics.mae_c.toFixed(2)}°C`
                  : "—"}
              </strong>
            </article>
            <article>
              <span>RMSE globale</span>
              <strong>
                {data.metrics.rmse_c !== null
                  ? `${data.metrics.rmse_c.toFixed(2)}°C`
                  : "—"}
              </strong>
            </article>
            <article>
              <span>Biais global</span>
              <strong>
                {data.metrics.bias_c !== null
                  ? `${data.metrics.bias_c.toFixed(2)}°C`
                  : "—"}
              </strong>
            </article>
          </section>

          <section className="panel">
            <div className="panelHeader">
              <div>
                <h2>Précision par horizon</h2>
                <p>
                  Le calcul concerne la trajectoire BASELINE, donc
                  l’évolution naturelle mesurée de la maison.
                </p>
              </div>
              <span
                className={
                  data.readiness.enough_data
                    ? "ready"
                    : "waiting"
                }
              >
                {data.readiness.enough_data
                  ? "Données suffisantes"
                  : `${data.match_count}/${data.readiness.minimum_matches} minimum`}
              </span>
            </div>

            <div className="table">
              <div className="row headerRow">
                <span>Horizon</span>
                <span>Mesures</span>
                <span>MAE</span>
                <span>RMSE</span>
                <span>Biais</span>
              </div>

              {rows.length === 0 && (
                <p className="empty">
                  Les premières correspondances apparaîtront lorsque les
                  horizons prévus auront été atteints.
                </p>
              )}

              {rows.map(([horizon, metric]) => (
                <div className="row" key={horizon}>
                  <strong>{horizonLabel(horizon)}</strong>
                  <span>{metric.sample_count}</span>
                  <span>{metric.mae_c.toFixed(2)}°C</span>
                  <span>{metric.rmse_c.toFixed(2)}°C</span>
                  <span>{metric.bias_c.toFixed(2)}°C</span>
                </div>
              ))}
            </div>
          </section>

          <section className="panel notice">
            <h2>Rôle de cette étape</h2>
            <p>
              Ces écarts alimenteront RC3.6 pour proposer une calibration
              réellement fondée sur les performances observées du modèle.
              Aucune modification n’est appliquée automatiquement.
            </p>
          </section>
        </>
      )}

      <style jsx>{`
        .page {
          min-height: 100vh;
          padding: 32px;
          color: #f4f7fb;
          background:
            radial-gradient(circle at top right, rgba(59, 189, 255, 0.17), transparent 32%),
            #07101f;
        }

        header,
        .panelHeader {
          display: flex;
          justify-content: space-between;
          gap: 24px;
          align-items: flex-start;
        }

        .eyebrow {
          color: #62c7ff;
          letter-spacing: 0.14em;
          text-transform: uppercase;
          font-size: 12px;
        }

        h1 {
          margin: 6px 0 12px;
          font-size: clamp(32px, 5vw, 56px);
        }

        .subtitle,
        .panelHeader p,
        .empty {
          max-width: 720px;
          color: #9eacc3;
        }

        .badge,
        .ready,
        .waiting {
          border-radius: 999px;
          padding: 10px 14px;
          white-space: nowrap;
        }

        .badge,
        .ready {
          color: #72e0b1;
          border: 1px solid rgba(114, 224, 177, 0.35);
          background: rgba(30, 130, 91, 0.14);
        }

        .waiting {
          color: #ffc96b;
          border: 1px solid rgba(255, 201, 107, 0.35);
          background: rgba(133, 86, 12, 0.18);
        }

        .metrics {
          display: grid;
          grid-template-columns: repeat(4, minmax(0, 1fr));
          gap: 16px;
          margin: 28px 0 20px;
        }

        .metrics article,
        .panel {
          border: 1px solid rgba(148, 170, 205, 0.16);
          background: rgba(14, 27, 48, 0.78);
          box-shadow: 0 20px 60px rgba(0, 0, 0, 0.22);
          backdrop-filter: blur(14px);
        }

        .metrics article {
          border-radius: 18px;
          padding: 20px;
        }

        .metrics span {
          color: #91a2bd;
        }

        .metrics strong {
          display: block;
          margin-top: 8px;
          font-size: 26px;
        }

        .panel {
          border-radius: 22px;
          padding: 24px;
          margin-bottom: 20px;
        }

        .table {
          margin-top: 18px;
        }

        .row {
          display: grid;
          grid-template-columns: 1.2fr repeat(4, 1fr);
          gap: 18px;
          padding: 13px 0;
          border-top: 1px solid rgba(148, 170, 205, 0.1);
        }

        .headerRow {
          color: #91a2bd;
          border-top: 0;
        }

        .notice {
          border-color: rgba(98, 199, 255, 0.25);
        }

        .error {
          color: #ffb2b2;
          border-color: rgba(255, 102, 102, 0.4);
        }

        @media (max-width: 850px) {
          .page {
            padding: 20px;
          }

          header,
          .panelHeader {
            flex-direction: column;
          }

          .metrics {
            grid-template-columns: repeat(2, minmax(0, 1fr));
          }

          .table {
            overflow-x: auto;
          }

          .row {
            min-width: 650px;
          }
        }
      `}</style>
    </main>
  );
}
