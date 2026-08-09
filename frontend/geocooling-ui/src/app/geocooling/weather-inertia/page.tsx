"use client";

import { useEffect, useMemo, useState } from "react";

type Point = {
  horizon_minutes: number;
  predicted_indoor_temperature_c: number;
  predicted_mass_temperature_c: number;
  outdoor_temperature_c: number;
  confidence: number;
  uncertainty_c: number;
};

type Trajectory = {
  scenario: string;
  points: Point[];
};

type Prediction = {
  generated_at: string;
  horizons_minutes: number[];
  model: Record<string, number>;
  input: {
    indoor_temperature_c: number;
    outdoor_temperature_c: number;
    mass_temperature_c: number;
    weather_points: number;
  };
  trajectories: Trajectory[];
  sources?: {
    context?: string;
    weather?: string | null;
  };
};

const API_BASE =
  process.env.NEXT_PUBLIC_GEOCOOLING_API_URL ?? "";

function labelForMinutes(minutes: number): string {
  if (minutes < 60) return `${minutes} min`;
  if (minutes < 1440) return `${minutes / 60} h`;
  return `${minutes / 1440} j`;
}

function trajectoryName(value: string): string {
  return {
    BASELINE: "Sans géocooling",
    SOFT_COOLING: "Rafraîchissement modéré",
    FULL_COOLING: "Rafraîchissement nominal",
  }[value] ?? value;
}

function MiniChart({ trajectories }: { trajectories: Trajectory[] }) {
  const width = 920;
  const height = 340;
  const padding = 48;

  const allPoints = trajectories.flatMap((item) => item.points);
  const temperatures = allPoints.flatMap((item) => [
    item.predicted_indoor_temperature_c,
    item.outdoor_temperature_c,
  ]);
  const minTemperature = Math.floor(Math.min(...temperatures) - 1);
  const maxTemperature = Math.ceil(Math.max(...temperatures) + 1);
  const maxHorizon = Math.max(
    ...allPoints.map((item) => item.horizon_minutes),
  );

  const x = (minutes: number) =>
    padding +
    (minutes / maxHorizon) * (width - padding * 2);

  const y = (temperature: number) =>
    height -
    padding -
    ((temperature - minTemperature) /
      Math.max(1, maxTemperature - minTemperature)) *
      (height - padding * 2);

  return (
    <div className="chartWrap">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="Prévision thermique sur 48 heures"
      >
        {[minTemperature, (minTemperature + maxTemperature) / 2, maxTemperature].map(
          (temperature) => (
            <g key={temperature}>
              <line
                x1={padding}
                x2={width - padding}
                y1={y(temperature)}
                y2={y(temperature)}
                className="grid"
              />
              <text x={8} y={y(temperature) + 5} className="axisText">
                {temperature.toFixed(1)}°C
              </text>
            </g>
          ),
        )}

        {trajectories.map((trajectory, index) => {
          const path = trajectory.points
            .map(
              (point, pointIndex) =>
                `${pointIndex === 0 ? "M" : "L"} ${x(
                  point.horizon_minutes,
                )} ${y(point.predicted_indoor_temperature_c)}`,
            )
            .join(" ");

          return (
            <path
              key={trajectory.scenario}
              d={path}
              className={`trajectory trajectory${index + 1}`}
            />
          );
        })}

        {allPoints
          .filter((_, index) => index < trajectories[0]?.points.length)
          .map((point) => (
            <text
              key={point.horizon_minutes}
              x={x(point.horizon_minutes)}
              y={height - 12}
              textAnchor="middle"
              className="axisText"
            >
              {labelForMinutes(point.horizon_minutes)}
            </text>
          ))}
      </svg>
    </div>
  );
}

export default function WeatherInertiaPage() {
  const [data, setData] = useState<Prediction | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;

    const load = async () => {
      try {
        const response = await fetch(
          `${API_BASE}/geocooling/rc3/weather-inertia/live`,
          { cache: "no-store" },
        );

        if (!response.ok) {
          throw new Error(`API ${response.status}`);
        }

        const payload = (await response.json()) as Prediction;

        if (active) {
          setData(payload);
          setError(null);
        }
      } catch (caught) {
        if (active) {
          setError(
            caught instanceof Error
              ? caught.message
              : "Prévision indisponible",
          );
        }
      } finally {
        if (active) setLoading(false);
      }
    };

    void load();
    const timer = window.setInterval(load, 60_000);

    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  const summaries = useMemo(() => {
    if (!data) return [];

    return data.trajectories.map((trajectory) => {
      const last = trajectory.points.at(-1);
      const peak = Math.max(
        ...trajectory.points.map(
          (point) => point.predicted_indoor_temperature_c,
        ),
      );

      return {
        scenario: trajectory.scenario,
        final: last?.predicted_indoor_temperature_c,
        peak,
        confidence: last?.confidence,
        uncertainty: last?.uncertainty_c,
      };
    });
  }, [data]);

  return (
    <main className="predictorPage">
      <header className="hero">
        <div>
          <p className="eyebrow">RC3.5 · Mode Shadow</p>
          <h1>Prévision météo & inertie</h1>
          <p className="subtitle">
            Trajectoires thermiques de la maison sur 48 heures,
            recalculées avec la météo actuelle et les prévisions.
          </p>
        </div>
        <div className="statusBadge">
          Aucun pilotage matériel
        </div>
      </header>

      {loading && <section className="panel">Chargement…</section>}

      {error && (
        <section className="panel error">
          Prévision indisponible : {error}
        </section>
      )}

      {data && (
        <>
          <section className="metrics">
            <article className="metric">
              <span>Intérieur</span>
              <strong>{data.input.indoor_temperature_c.toFixed(1)}°C</strong>
            </article>
            <article className="metric">
              <span>Extérieur</span>
              <strong>{data.input.outdoor_temperature_c.toFixed(1)}°C</strong>
            </article>
            <article className="metric">
              <span>Masse thermique</span>
              <strong>{data.input.mass_temperature_c.toFixed(1)}°C</strong>
            </article>
            <article className="metric">
              <span>Points météo</span>
              <strong>{data.input.weather_points}</strong>
            </article>
          </section>

          <section className="panel">
            <div className="panelHeader">
              <div>
                <h2>Trajectoires à 48 heures</h2>
                <p>
                  Sans géocooling, rafraîchissement modéré et nominal.
                </p>
              </div>
              <small>
                Actualisé{" "}
                {new Date(data.generated_at).toLocaleTimeString("fr-FR")}
              </small>
            </div>

            <MiniChart trajectories={data.trajectories} />

            <div className="legend">
              {data.trajectories.map((trajectory, index) => (
                <span key={trajectory.scenario}>
                  <i className={`dot dot${index + 1}`} />
                  {trajectoryName(trajectory.scenario)}
                </span>
              ))}
            </div>
          </section>

          <section className="scenarioGrid">
            {summaries.map((summary) => (
              <article className="scenarioCard" key={summary.scenario}>
                <p>{trajectoryName(summary.scenario)}</p>
                <strong>
                  {summary.final?.toFixed(1)}°C
                  <small> à 48 h</small>
                </strong>
                <dl>
                  <div>
                    <dt>Pic prévu</dt>
                    <dd>{summary.peak.toFixed(1)}°C</dd>
                  </div>
                  <div>
                    <dt>Confiance</dt>
                    <dd>
                      {summary.confidence
                        ? `${Math.round(summary.confidence * 100)} %`
                        : "—"}
                    </dd>
                  </div>
                  <div>
                    <dt>Incertitude</dt>
                    <dd>± {summary.uncertainty?.toFixed(1)}°C</dd>
                  </div>
                </dl>
              </article>
            ))}
          </section>

          <section className="panel modelPanel">
            <h2>Modèle thermique utilisé</h2>
            <div className="modelGrid">
              <span>
                Inertie rapide
                <strong>{data.model.fast_time_constant_hours} h</strong>
              </span>
              <span>
                Inertie lente
                <strong>{data.model.slow_time_constant_hours} h</strong>
              </span>
              <span>
                Couplage masse
                <strong>{data.model.mass_coupling}</strong>
              </span>
              <span>
                Confiance initiale
                <strong>
                  {Math.round(data.model.model_confidence * 100)} %
                </strong>
              </span>
            </div>
          </section>
        </>
      )}

      <style jsx>{`
        .predictorPage {
          min-height: 100vh;
          padding: 32px;
          background:
            radial-gradient(circle at top right, rgba(73, 139, 255, 0.14), transparent 32%),
            #07101f;
          color: #f4f7fb;
        }

        .hero,
        .panelHeader,
        .metrics,
        .scenarioGrid,
        .modelGrid {
          display: flex;
          gap: 20px;
        }

        .hero,
        .panelHeader {
          justify-content: space-between;
          align-items: flex-start;
        }

        .eyebrow {
          margin: 0 0 8px;
          letter-spacing: 0.14em;
          text-transform: uppercase;
          color: #83b8ff;
          font-size: 12px;
        }

        h1 {
          margin: 0;
          font-size: clamp(32px, 5vw, 58px);
          line-height: 1;
        }

        h2 {
          margin: 0;
        }

        .subtitle,
        .panelHeader p {
          color: #9eacc3;
          max-width: 700px;
        }

        .statusBadge {
          padding: 10px 14px;
          border: 1px solid rgba(91, 216, 165, 0.35);
          border-radius: 999px;
          color: #72e0b1;
          background: rgba(30, 130, 91, 0.14);
          white-space: nowrap;
        }

        .metrics {
          margin: 28px 0 20px;
          flex-wrap: wrap;
        }

        .metric,
        .panel,
        .scenarioCard {
          border: 1px solid rgba(148, 170, 205, 0.16);
          background: rgba(14, 27, 48, 0.78);
          box-shadow: 0 20px 60px rgba(0, 0, 0, 0.22);
          backdrop-filter: blur(14px);
        }

        .metric {
          flex: 1 1 180px;
          padding: 20px;
          border-radius: 18px;
        }

        .metric span,
        .scenarioCard p,
        dt,
        small {
          color: #91a2bd;
        }

        .metric strong {
          display: block;
          margin-top: 8px;
          font-size: 28px;
        }

        .panel {
          padding: 24px;
          border-radius: 22px;
          margin-bottom: 20px;
        }

        .error {
          border-color: rgba(255, 102, 102, 0.4);
          color: #ffb2b2;
        }

        .chartWrap {
          overflow-x: auto;
          margin-top: 20px;
        }

        svg {
          width: 100%;
          min-width: 760px;
        }

        :global(.grid) {
          stroke: rgba(153, 175, 210, 0.13);
          stroke-width: 1;
        }

        :global(.axisText) {
          fill: #8090a8;
          font-size: 12px;
        }

        :global(.trajectory) {
          fill: none;
          stroke-width: 4;
          stroke-linecap: round;
          stroke-linejoin: round;
        }

        :global(.trajectory1) {
          stroke: #ffbd5a;
        }

        :global(.trajectory2) {
          stroke: #63c5ff;
        }

        :global(.trajectory3) {
          stroke: #75e2ad;
        }

        .legend {
          display: flex;
          flex-wrap: wrap;
          gap: 18px;
          color: #b8c5d8;
        }

        .legend span {
          display: inline-flex;
          align-items: center;
          gap: 8px;
        }

        .dot {
          width: 10px;
          height: 10px;
          border-radius: 50%;
        }

        .dot1 {
          background: #ffbd5a;
        }

        .dot2 {
          background: #63c5ff;
        }

        .dot3 {
          background: #75e2ad;
        }

        .scenarioGrid {
          align-items: stretch;
          margin-bottom: 20px;
        }

        .scenarioCard {
          flex: 1;
          padding: 22px;
          border-radius: 20px;
        }

        .scenarioCard strong {
          font-size: 32px;
        }

        .scenarioCard strong small {
          font-size: 13px;
          font-weight: 500;
        }

        dl {
          margin: 20px 0 0;
        }

        dl div {
          display: flex;
          justify-content: space-between;
          padding: 9px 0;
          border-top: 1px solid rgba(148, 170, 205, 0.1);
        }

        dd {
          margin: 0;
        }

        .modelGrid {
          flex-wrap: wrap;
          margin-top: 18px;
        }

        .modelGrid span {
          flex: 1 1 180px;
          color: #91a2bd;
        }

        .modelGrid strong {
          display: block;
          color: #f4f7fb;
          margin-top: 4px;
        }

        @media (max-width: 800px) {
          .predictorPage {
            padding: 20px;
          }

          .hero,
          .scenarioGrid {
            flex-direction: column;
          }

          .statusBadge {
            white-space: normal;
          }
        }
      `}</style>
    </main>
  );
}
