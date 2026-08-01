import type { GeoCoolingSnapshot } from "@/types/geocooling";
import { Panel } from "@/components/ui/Panel";
import { StatusBadge } from "@/components/ui/StatusBadge";

type ThermalCardProps = {
  snapshot: GeoCoolingSnapshot | null;
};

type ThermalState = {
  label: string;
  tone: "success" | "warning" | "danger" | "neutral";
  className: string;
  description: string;
};

function validNumber(
  value: number | null | undefined,
): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function format(
  value: number | null | undefined,
  digits = 1,
): string {
  return validNumber(value)
    ? value.toFixed(digits)
    : "—";
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

function thermalState(
  margin: number | null,
  safetySafe: boolean | null | undefined,
): ThermalState {
  if (safetySafe === false) {
    return {
      label: "BLOQUÉ",
      tone: "danger",
      className: "is-critical",
      description:
        "Le contrôleur signale une condition de sécurité.",
    };
  }

  if (margin === null) {
    return {
      label: "INCOMPLET",
      tone: "neutral",
      className: "is-neutral",
      description:
        "Les mesures disponibles ne permettent pas de calculer la marge de condensation.",
    };
  }

  if (margin < 2) {
    return {
      label: "RISQUE ÉLEVÉ",
      tone: "danger",
      className: "is-critical",
      description:
        "La température de départ est trop proche du point de rosée.",
    };
  }

  if (margin < 3) {
    return {
      label: "VIGILANCE",
      tone: "warning",
      className: "is-warning",
      description:
        "La marge de condensation est inférieure à la cible de sécurité.",
    };
  }

  return {
    label: "MARGE SÛRE",
    tone: "success",
    className: "is-good",
    description:
      "La température de départ reste suffisamment au-dessus du point de rosée.",
  };
}

function comfortState(
  temperature: number | null | undefined,
): {
  label: string;
  className: string;
} {
  if (!validNumber(temperature)) {
    return {
      label: "INCONNU",
      className: "is-neutral",
    };
  }

  if (temperature >= 26) {
    return {
      label: "CHAUD",
      className: "is-warning",
    };
  }

  if (temperature >= 24) {
    return {
      label: "CONFORT HAUT",
      className: "is-information",
    };
  }

  if (temperature >= 20) {
    return {
      label: "CONFORT",
      className: "is-good",
    };
  }

  return {
    label: "FRAIS",
    className: "is-information",
  };
}

export function ThermalCard({
  snapshot,
}: ThermalCardProps) {
  const calculatedDewPoint = dewPoint(
    snapshot?.indoorTemperature,
    snapshot?.humidity,
  );

  const condensationMargin =
    validNumber(snapshot?.supplyTemperature) &&
    calculatedDewPoint !== null
      ? snapshot.supplyTemperature - calculatedDewPoint
      : null;

  const hydraulicDelta =
    validNumber(snapshot?.returnTemperature) &&
    validNumber(snapshot?.supplyTemperature)
      ? snapshot.returnTemperature -
        snapshot.supplyTemperature
      : null;

  const state = thermalState(
    condensationMargin,
    snapshot?.safetySafe,
  );

  const comfort = comfortState(
    snapshot?.indoorTemperature,
  );

  const availableMeasurements = [
    snapshot?.indoorTemperature,
    snapshot?.humidity,
    snapshot?.supplyTemperature,
    snapshot?.returnTemperature,
  ].filter(validNumber).length;

  return (
    <Panel
      title="Thermique & condensation"
      subtitle="Confort intérieur et sécurité du plancher"
      icon="◐"
      className="gc-thermal-console"
      action={
        <StatusBadge
          label={state.label}
          tone={state.tone}
          pulse={state.tone === "danger"}
        />
      }
    >
      <section className="gc-thermal-summary">
        <article className="gc-thermal-primary">
          <span className="gc-thermal-label">
            TEMPÉRATURE INTÉRIEURE
          </span>

          <div className="gc-thermal-primary__value">
            <strong>
              {format(snapshot?.indoorTemperature)}
            </strong>

            <span>°C</span>
          </div>

          <div
            className={`gc-thermal-state ${comfort.className}`}
          >
            <span />
            {comfort.label}
          </div>
        </article>

        <article className="gc-thermal-primary">
          <span className="gc-thermal-label">
            HUMIDITÉ RELATIVE
          </span>

          <div className="gc-thermal-primary__value">
            <strong>
              {format(snapshot?.humidity)}
            </strong>

            <span>%</span>
          </div>

          <small>
            Mesure moyenne du bâtiment
          </small>
        </article>
      </section>

      <section className="gc-condensation-panel">
        <header>
          <div>
            <span className="gc-thermal-label">
              SÉCURITÉ CONDENSATION
            </span>

            <strong>{state.description}</strong>
          </div>

          <div
            className={`gc-condensation-margin ${state.className}`}
          >
            <span>MARGE</span>

            <strong>
              {condensationMargin === null
                ? "—"
                : condensationMargin.toFixed(1)}
            </strong>

            <small>°C</small>
          </div>
        </header>

        <div className="gc-condensation-scale">
          <div className="gc-condensation-scale__labels">
            <span>RISQUE</span>
            <span>VIGILANCE</span>
            <span>SÛR</span>
          </div>

          <div className="gc-condensation-scale__track">
            <div className="is-critical" />
            <div className="is-warning" />
            <div className="is-good" />

            {condensationMargin !== null ? (
              <span
                className="gc-condensation-scale__marker"
                style={{
                  left: `${Math.min(
                    100,
                    Math.max(
                      0,
                      (condensationMargin / 6) * 100,
                    ),
                  )}%`,
                }}
              />
            ) : null}
          </div>
        </div>
      </section>

      <section className="gc-thermal-metrics">
        <article>
          <span>POINT DE ROSÉE</span>

          <strong>
            {calculatedDewPoint === null
              ? "—"
              : calculatedDewPoint.toFixed(1)}
          </strong>

          <small>°C calculé</small>
        </article>

        <article>
          <span>DÉPART PLANCHER</span>

          <strong>
            {format(snapshot?.supplyTemperature)}
          </strong>

          <small>°C</small>
        </article>

        <article>
          <span>RETOUR PLANCHER</span>

          <strong>
            {format(snapshot?.returnTemperature)}
          </strong>

          <small>°C</small>
        </article>

        <article>
          <span>DELTA PLANCHER</span>

          <strong>
            {hydraulicDelta === null
              ? "—"
              : hydraulicDelta.toFixed(1)}
          </strong>

          <small>°C retour − départ</small>
        </article>
      </section>

      <footer className="gc-thermal-footer">
        <div>
          <span
            className={
              availableMeasurements === 4
                ? "is-positive"
                : "is-warning"
            }
          />

          {availableMeasurements}/4 mesures disponibles
        </div>

        <div>
          <span
            className={
              snapshot?.safetySafe === false
                ? "is-negative"
                : "is-positive"
            }
          />

          Sécurité
          {snapshot?.safetySafe === false
            ? " bloquante"
            : " non bloquante"}
        </div>
      </footer>
    </Panel>
  );
}
