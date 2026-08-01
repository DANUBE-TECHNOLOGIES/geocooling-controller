"use client";

import Link from "next/link";
import type { GeoCoolingSnapshot } from "@/types/geocooling";
import { AppShell } from "@/components/layout/AppShell";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useGeoCooling } from "@/hooks/useGeoCooling";

type ForecastPoint = {
  hour: number;
  indoorTemperature: number | null;
  supplyTemperature: number | null;
  returnTemperature: number | null;
  confidence: number;
  circuitActive: boolean;
};

type ForecastState = {
  label: string;
  tone: "success" | "warning" | "danger" | "neutral";
  description: string;
};

function validNumber(
  value: number | null | undefined,
): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function clamp(
  value: number,
  minimum: number,
  maximum: number,
): number {
  return Math.min(maximum, Math.max(minimum, value));
}

function dewPoint(
  temperature: number | null | undefined,
  humidity: number | null | undefined,
): number | null {
  if (
    !validNumber(temperature) ||
    !validNumber(humidity) ||
    humidity <= 0 ||
    humidity > 100
  ) {
    return null;
  }

  const a = 17.62;
  const b = 243.12;

  const gamma =
    Math.log(humidity / 100) +
    (a * temperature) / (b + temperature);

  return (b * gamma) / (a - gamma);
}

function buildForecast(
  snapshot: GeoCoolingSnapshot | null,
): ForecastPoint[] {
  const indoor =
    snapshot?.indoorTemperature ?? null;

  const supply =
    snapshot?.supplyTemperature ?? null;

  const returnTemperature =
    snapshot?.returnTemperature ?? null;

  const active = Boolean(
    snapshot?.pumpRunning &&
    snapshot?.valveOpen &&
    snapshot?.safetySafe !== false,
  );

  const initialConfidence = clamp(
    snapshot?.decision.confidence ?? 0,
    0,
    100,
  );

  return Array.from(
    { length: 13 },
    (_, index): ForecastPoint => {
      const hour = index;

      const coolingEffect =
        active
          ? Math.min(1.8, hour * 0.15)
          : 0;

      const passiveDrift =
        active
          ? 0
          : Math.min(1.2, hour * 0.1);

      const projectedIndoor =
        validNumber(indoor)
          ? indoor - coolingEffect + passiveDrift
          : null;

      const projectedSupply =
        validNumber(supply)
          ? supply +
            (active
              ? Math.min(0.8, hour * 0.06)
              : Math.min(1.5, hour * 0.12))
          : null;

      const projectedReturn =
        validNumber(returnTemperature)
          ? returnTemperature +
            (active
              ? Math.min(0.6, hour * 0.05)
              : Math.min(1.3, hour * 0.1))
          : null;

      return {
        hour,
        indoorTemperature:
          projectedIndoor === null
            ? null
            : Number(projectedIndoor.toFixed(2)),

        supplyTemperature:
          projectedSupply === null
            ? null
            : Number(projectedSupply.toFixed(2)),

        returnTemperature:
          projectedReturn === null
            ? null
            : Number(projectedReturn.toFixed(2)),

        confidence: Math.round(
          clamp(
            initialConfidence - hour * 3.5,
            20,
            100,
          ),
        ),

        circuitActive: active,
      };
    },
  );
}

function forecastState(
  snapshot: GeoCoolingSnapshot | null,
  margin: number | null,
): ForecastState {
  if (!snapshot) {
    return {
      label: "INDISPONIBLE",
      tone: "danger",
      description:
        "Aucune donnée ne permet de calculer une projection.",
    };
  }

  if (snapshot.safetySafe === false) {
    return {
      label: "BLOQUÉ",
      tone: "danger",
      description:
        "La projection est limitée par une sécurité active.",
    };
  }

  if (margin !== null && margin < 3) {
    return {
      label: "VIGILANCE",
      tone: "warning",
      description:
        "La marge de condensation impose une surveillance renforcée.",
    };
  }

  if (
    snapshot.pumpRunning &&
    snapshot.valveOpen
  ) {
    return {
      label: "RAFRAÎCHISSEMENT",
      tone: "success",
      description:
        "La projection tient compte du fonctionnement actuel du circuit.",
    };
  }

  return {
    label: "VEILLE",
    tone: "neutral",
    description:
      "La projection suppose le maintien du circuit à l’arrêt.",
  };
}

function formatValue(
  value: number | null,
): string {
  return value === null
    ? "—"
    : value.toFixed(1);
}

function pathForSeries(
  points: ForecastPoint[],
  selector: (
    point: ForecastPoint,
  ) => number | null,
  minimum: number,
  maximum: number,
): string {
  const width = 1000;
  const height = 260;
  const span = Math.max(1, maximum - minimum);

  return points
    .map((point, index) => {
      const value = selector(point);

      if (!validNumber(value)) {
        return null;
      }

      const x =
        points.length <= 1
          ? 0
          : (index / (points.length - 1)) * width;

      const y =
        height -
        ((value - minimum) / span) * height;

      return {
        x,
        y,
      };
    })
    .filter(
      (
        point,
      ): point is {
        x: number;
        y: number;
      } => point !== null,
    )
    .map(
      (point, index) =>
        `${index === 0 ? "M" : "L"} ${point.x.toFixed(
          1,
        )} ${point.y.toFixed(1)}`,
    )
    .join(" ");
}

export default function ForecastPage() {
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

  const calculatedDewPoint = dewPoint(
    snapshot?.indoorTemperature,
    snapshot?.humidity,
  );

  const condensationMargin =
    calculatedDewPoint !== null &&
    validNumber(snapshot?.supplyTemperature)
      ? snapshot.supplyTemperature -
        calculatedDewPoint
      : null;

  const forecast = buildForecast(snapshot);

  const state = forecastState(
    snapshot,
    condensationMargin,
  );

  const temperatureValues =
    forecast.flatMap((point) => [
      point.indoorTemperature,
      point.supplyTemperature,
      point.returnTemperature,
    ]).filter(validNumber);

  const minimum =
    temperatureValues.length > 0
      ? Math.floor(
          Math.min(...temperatureValues) - 1,
        )
      : 10;

  const maximum =
    temperatureValues.length > 0
      ? Math.ceil(
          Math.max(...temperatureValues) + 1,
        )
      : 30;

  const indoorPath = pathForSeries(
    forecast,
    (point) => point.indoorTemperature,
    minimum,
    maximum,
  );

  const supplyPath = pathForSeries(
    forecast,
    (point) => point.supplyTemperature,
    minimum,
    maximum,
  );

  const returnPath = pathForSeries(
    forecast,
    (point) => point.returnTemperature,
    minimum,
    maximum,
  );

  const finalPoint =
    forecast.at(-1) ?? null;

  const projectedDrop =
    finalPoint &&
    validNumber(snapshot?.indoorTemperature) &&
    validNumber(finalPoint.indoorTemperature)
      ? snapshot.indoorTemperature -
        finalPoint.indoorTemperature
      : null;

  return (
    <AppShell
      connected={connected}
      mode={String(
        snapshot?.mode ?? "INCONNU",
      )}
      refreshing={refreshing}
      lastUpdate={lastUpdate}
      generatedAt={snapshot?.generatedAt}
      responseTime={responseTime}
      onRefresh={() => {
        void refresh();
      }}
    >
      <section className="gc-page-header">
        <div>
          <p className="gc-page-header__eyebrow">
            PROJECTION THERMIQUE LOCALE
          </p>

          <h2>Prévision GeoCooling</h2>

          <p>
            Projection indicative sur douze heures
            construite à partir du snapshot courant,
            de l’état hydraulique et de la confiance
            du Brain.
          </p>
        </div>

        <div className="gc-page-header__actions">
          <Link
            href="/"
            className="gc-page-link"
          >
            ← Dashboard
          </Link>

          <StatusBadge
            label={state.label}
            tone={state.tone}
            pulse={state.tone === "success"}
          />
        </div>
      </section>

      <section className="gc-forecast-warning">
        <strong>
          Projection locale, non météorologique
        </strong>

        <p>
          Ce module n’utilise pas encore de données
          météo extérieures ni de modèle thermique
          persistant. Il extrapole uniquement la
          situation courante et ne doit pas être
          interprété comme une prévision certifiée.
        </p>
      </section>

      {loading && !snapshot ? (
        <section className="gc-loading-state">
          <div className="gc-loading-spinner" />

          <div>
            <strong>
              Calcul de la projection…
            </strong>

            <span>
              Chargement du premier snapshot.
            </span>
          </div>
        </section>
      ) : null}

      <section className="gc-forecast-kpis">
        <article>
          <span>TEMPÉRATURE ACTUELLE</span>

          <strong>
            {formatValue(
              snapshot?.indoorTemperature ?? null,
            )} °C
          </strong>

          <small>Ambiance intérieure</small>
        </article>

        <article>
          <span>PROJECTION À 12 H</span>

          <strong>
            {formatValue(
              finalPoint?.indoorTemperature ?? null,
            )} °C
          </strong>

          <small>
            Hypothèse de fonctionnement constant
          </small>
        </article>

        <article>
          <span>ÉVOLUTION PROJETÉE</span>

          <strong>
            {projectedDrop === null
              ? "—"
              : `${projectedDrop >= 0 ? "−" : "+"}${Math.abs(
                  projectedDrop,
                ).toFixed(1)} °C`}
          </strong>

          <small>
            Variation ambiance sur 12 h
          </small>
        </article>

        <article>
          <span>MARGE CONDENSATION</span>

          <strong>
            {condensationMargin === null
              ? "—"
              : `${condensationMargin.toFixed(1)} °C`}
          </strong>

          <small>
            Départ moins point de rosée
          </small>
        </article>
      </section>

      <section className="gc-forecast-chart">
        <header>
          <div>
            <span className="gc-page-header__eyebrow">
              HORIZON 12 HEURES
            </span>

            <h3>
              Projection des températures
            </h3>
          </div>

          <div className="gc-forecast-legend">
            <span className="is-indoor">
              <i />
              Intérieur
            </span>

            <span className="is-supply">
              <i />
              Départ
            </span>

            <span className="is-return">
              <i />
              Retour
            </span>
          </div>
        </header>

        <div className="gc-forecast-chart__canvas">
          <div className="gc-forecast-axis">
            <span>{maximum} °C</span>
            <span>
              {Math.round(
                (maximum + minimum) / 2,
              )} °C
            </span>
            <span>{minimum} °C</span>
          </div>

          <svg
            viewBox="0 0 1000 260"
            preserveAspectRatio="none"
            role="img"
            aria-label="Projection thermique GeoCooling sur douze heures"
          >
            <g className="gc-forecast-grid">
              <path d="M0 0 H1000" />
              <path d="M0 65 H1000" />
              <path d="M0 130 H1000" />
              <path d="M0 195 H1000" />
              <path d="M0 260 H1000" />

              <path d="M0 0 V260" />
              <path d="M250 0 V260" />
              <path d="M500 0 V260" />
              <path d="M750 0 V260" />
              <path d="M1000 0 V260" />
            </g>

            {indoorPath ? (
              <path
                d={indoorPath}
                className="gc-forecast-series is-indoor"
              />
            ) : null}

            {supplyPath ? (
              <path
                d={supplyPath}
                className="gc-forecast-series is-supply"
              />
            ) : null}

            {returnPath ? (
              <path
                d={returnPath}
                className="gc-forecast-series is-return"
              />
            ) : null}
          </svg>

          <div className="gc-forecast-time-axis">
            <span>Maintenant</span>
            <span>+3 h</span>
            <span>+6 h</span>
            <span>+9 h</span>
            <span>+12 h</span>
          </div>
        </div>
      </section>

      <section className="gc-forecast-grid-layout">
        <article className="gc-forecast-table-panel">
          <header>
            <div>
              <span className="gc-page-header__eyebrow">
                SCÉNARIO CALCULÉ
              </span>

              <h3>
                Évolution horaire
              </h3>
            </div>

            <strong>
              {forecast.length} points
            </strong>
          </header>

          <div className="gc-forecast-table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Horizon</th>
                  <th>Intérieur</th>
                  <th>Départ</th>
                  <th>Retour</th>
                  <th>Confiance</th>
                  <th>Circuit</th>
                </tr>
              </thead>

              <tbody>
                {forecast.map((point) => (
                  <tr key={point.hour}>
                    <td>
                      {point.hour === 0
                        ? "Maintenant"
                        : `+${point.hour} h`}
                    </td>

                    <td>
                      {formatValue(
                        point.indoorTemperature,
                      )} °C
                    </td>

                    <td>
                      {formatValue(
                        point.supplyTemperature,
                      )} °C
                    </td>

                    <td>
                      {formatValue(
                        point.returnTemperature,
                      )} °C
                    </td>

                    <td>
                      {point.confidence} %
                    </td>

                    <td>
                      <span
                        className={
                          point.circuitActive
                            ? "gc-table-status is-positive"
                            : "gc-table-status is-neutral"
                        }
                      >
                        {point.circuitActive
                          ? "ACTIF"
                          : "ARRÊT"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>

        <article className="gc-forecast-assumptions">
          <header>
            <span className="gc-page-header__eyebrow">
              HYPOTHÈSES DU MODÈLE
            </span>

            <h3>
              Conditions de calcul
            </h3>
          </header>

          <div>
            <article>
              <span>01</span>

              <div>
                <strong>
                  État hydraulique constant
                </strong>

                <small>
                  La pompe et la vanne sont supposées
                  conserver leur état actuel.
                </small>
              </div>
            </article>

            <article>
              <span>02</span>

              <div>
                <strong>
                  Absence de météo extérieure
                </strong>

                <small>
                  Aucun apport solaire ni température
                  extérieure n’est intégré.
                </small>
              </div>
            </article>

            <article>
              <span>03</span>

              <div>
                <strong>
                  Décroissance de confiance
                </strong>

                <small>
                  La confiance diminue progressivement
                  avec l’horizon de projection.
                </small>
              </div>
            </article>

            <article>
              <span>04</span>

              <div>
                <strong>
                  Modèle simplifié
                </strong>

                <small>
                  L’inertie réelle du bâtiment n’est
                  pas encore apprise par le backend.
                </small>
              </div>
            </article>
          </div>
        </article>
      </section>
    </AppShell>
  );
}
