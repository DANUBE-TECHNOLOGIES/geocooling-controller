"use client";

import { useEffect, useState } from "react";

type CalibrationReport = {
  status: string;
  sample_count: number;
  minimum_samples: number;
  metrics?: {
    mae_c?: number;
    bias_c?: number;
    median_error_c?: number;
    short_horizon_bias_c?: number;
    long_horizon_bias_c?: number;
  };
  current_model: Record<string, number>;
  proposal: Record<string, number>;
  activation: {
    automatic: boolean;
    requires_review: boolean;
  };
};

const API_BASE =
  process.env.NEXT_PUBLIC_GEOCOOLING_API_URL ?? "";

const LABELS: Record<string, string> = {
  fast_time_constant_hours: "Inertie rapide",
  slow_time_constant_hours: "Inertie lente",
  mass_coupling: "Couplage masse",
  solar_gain_c_per_hour_at_full_sun: "Gain solaire",
  soft_cooling_c_per_hour: "Efficacité rafraîchissement modéré",
  full_cooling_c_per_hour: "Efficacité rafraîchissement nominal",
  model_confidence: "Confiance du modèle",
};

function formatValue(key: string, value?: number): string {
  if (value === undefined || Number.isNaN(value)) return "—";

  if (key.includes("hours")) return `${value.toFixed(2)} h`;
  if (key === "model_confidence") {
    return `${Math.round(value * 100)} %`;
  }

  return value.toFixed(3);
}

export default function CalibrationPage() {
  const [data, setData] = useState<CalibrationReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const response = await fetch(
          `${API_BASE}/geocooling/rc3/calibration/proposal`,
          { cache: "no-store" },
        );

        if (!response.ok) {
          throw new Error(`API ${response.status}`);
        }

        setData((await response.json()) as CalibrationReport);
        setError(null);
      } catch (caught) {
        setError(
          caught instanceof Error
            ? caught.message
            : "Proposition indisponible",
        );
      }
    };

    void load();
  }, []);

  return (
    <main className="page">
      <header>
        <div>
          <p className="eyebrow">RC3.6 · Calibration passive</p>
          <h1>Auto-calibration du modèle</h1>
          <p className="subtitle">
            Analyse des écarts entre prévisions et mesures réelles.
            Toute modification reste soumise à validation.
          </p>
        </div>
        <span className="badge">Aucune activation automatique</span>
      </header>

      {error && <section className="panel error">{error}</section>}

      {!data && !error && (
        <section className="panel">Chargement de la proposition…</section>
      )}

      {data && (
        <>
          <section className="metrics">
            <article>
              <span>Statut</span>
              <strong>{data.status}</strong>
            </article>
            <article>
              <span>Échantillons</span>
              <strong>
                {data.sample_count} / {data.minimum_samples}
              </strong>
            </article>
            <article>
              <span>MAE</span>
              <strong>
                {data.metrics?.mae_c !== undefined
                  ? `${data.metrics.mae_c.toFixed(2)}°C`
                  : "—"}
              </strong>
            </article>
            <article>
              <span>Biais</span>
              <strong>
                {data.metrics?.bias_c !== undefined
                  ? `${data.metrics.bias_c.toFixed(2)}°C`
                  : "—"}
              </strong>
            </article>
          </section>

          <section className="panel">
            <h2>Comparaison des paramètres</h2>
            <div className="table">
              <div className="row headerRow">
                <span>Paramètre</span>
                <span>Actuel</span>
                <span>Proposé</span>
                <span>Écart</span>
              </div>

              {Object.keys(LABELS).map((key) => {
                const current = data.current_model[key];
                const proposal = data.proposal[key];
                const delta =
                  current !== undefined && proposal !== undefined
                    ? proposal - current
                    : undefined;

                return (
                  <div className="row" key={key}>
                    <span>{LABELS[key]}</span>
                    <span>{formatValue(key, current)}</span>
                    <span>{formatValue(key, proposal)}</span>
                    <span>
                      {delta !== undefined
                        ? `${delta >= 0 ? "+" : ""}${delta.toFixed(4)}`
                        : "—"}
                    </span>
                  </div>
                );
              })}
            </div>
          </section>

          <section className="panel notice">
            <h2>État de sécurité</h2>
            <p>
              Activation automatique :{" "}
              <strong>{data.activation.automatic ? "oui" : "non"}</strong>
            </p>
            <p>
              Validation humaine requise :{" "}
              <strong>
                {data.activation.requires_review ? "oui" : "non"}
              </strong>
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
            radial-gradient(circle at top left, rgba(125, 91, 255, 0.18), transparent 30%),
            #07101f;
        }

        header {
          display: flex;
          justify-content: space-between;
          gap: 24px;
          align-items: flex-start;
        }

        .eyebrow {
          color: #a895ff;
          letter-spacing: 0.14em;
          text-transform: uppercase;
          font-size: 12px;
        }

        h1 {
          margin: 6px 0 12px;
          font-size: clamp(32px, 5vw, 56px);
        }

        .subtitle {
          max-width: 720px;
          color: #9eacc3;
        }

        .badge {
          border: 1px solid rgba(114, 224, 177, 0.35);
          color: #72e0b1;
          border-radius: 999px;
          padding: 10px 14px;
          background: rgba(30, 130, 91, 0.14);
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
          grid-template-columns: 2fr 1fr 1fr 1fr;
          gap: 18px;
          padding: 13px 0;
          border-top: 1px solid rgba(148, 170, 205, 0.10);
        }

        .headerRow {
          color: #91a2bd;
          border-top: 0;
        }

        .notice {
          border-color: rgba(114, 224, 177, 0.25);
        }

        .error {
          color: #ffb2b2;
          border-color: rgba(255, 102, 102, 0.4);
        }

        @media (max-width: 850px) {
          .page {
            padding: 20px;
          }

          header {
            flex-direction: column;
          }

          .metrics {
            grid-template-columns: repeat(2, minmax(0, 1fr));
          }

          .row {
            grid-template-columns: 1.5fr 1fr 1fr;
          }

          .row span:last-child {
            display: none;
          }
        }
      `}</style>
    </main>
  );
}
