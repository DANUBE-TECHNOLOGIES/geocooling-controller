import type { GeoCoolingSnapshot } from "@/types/geocooling";

type Props = {
  snapshot: GeoCoolingSnapshot;
};

type ProcessState = {
  label: string;
  className: string;
  description: string;
};

function temperature(value: number | null): string {
  return typeof value === "number" && Number.isFinite(value)
    ? `${value.toFixed(1)} °C`
    : "--.- °C";
}

function statusLabel(
  value: boolean | null,
  active: string,
  inactive: string,
): string {
  if (value === null) {
    return "INCONNU";
  }

  return value ? active : inactive;
}

function processState(
  snapshot: GeoCoolingSnapshot,
): ProcessState {
  if (snapshot.safetySafe === false) {
    return {
      label: "ALARME",
      className: "is-fault",
      description: "Sécurité hydraulique bloquante",
    };
  }

  if (snapshot.deviceReady === false) {
    return {
      label: "NON PRÊT",
      className: "is-warning",
      description: "Matériel non disponible",
    };
  }

  if (snapshot.pumpRunning && snapshot.valveOpen) {
    return {
      label: "CIRCUIT ACTIF",
      className: "is-running",
      description: "Rafraîchissement en cours",
    };
  }

  if (snapshot.pumpRunning !== snapshot.valveOpen) {
    return {
      label: "TRANSITION",
      className: "is-warning",
      description: "Séquence hydraulique intermédiaire",
    };
  }

  return {
    label: "VEILLE",
    className: "is-idle",
    description: "Circuit hydraulique à l’arrêt",
  };
}

function sensorState(value: number | null): string {
  return typeof value === "number" && Number.isFinite(value)
    ? "is-available"
    : "is-missing";
}

export default function ScadaHydraulicDiagram({
  snapshot,
}: Props) {
  const safe = snapshot.safetySafe !== false;
  const sourceFlow = snapshot.valveOpen && safe;
  const floorFlow =
    snapshot.pumpRunning &&
    snapshot.valveOpen &&
    safe;

  const fault = snapshot.safetySafe === false;
  const state = processState(snapshot);

  const deltaSource =
    typeof snapshot.sourceInTemperature === "number" &&
    typeof snapshot.sourceOutTemperature === "number"
      ? (
          snapshot.sourceOutTemperature -
          snapshot.sourceInTemperature
        ).toFixed(1)
      : "--";

  const deltaFloor =
    typeof snapshot.supplyTemperature === "number" &&
    typeof snapshot.returnTemperature === "number"
      ? (
          snapshot.returnTemperature -
          snapshot.supplyTemperature
        ).toFixed(1)
      : "--";

  const sourceClass = sourceFlow
    ? "scada-v3-pipe scada-v3-pipe-source scada-v3-flow"
    : "scada-v3-pipe scada-v3-pipe-idle";

  const floorClass = floorFlow
    ? "scada-v3-pipe scada-v3-pipe-floor scada-v3-flow"
    : "scada-v3-pipe scada-v3-pipe-idle";

  const returnClass = floorFlow
    ? "scada-v3-pipe scada-v3-pipe-return scada-v3-flow-reverse"
    : "scada-v3-pipe scada-v3-pipe-idle";

  return (
    <section
      className={`scada-v3 ${fault ? "scada-v3-fault" : ""}`}
      data-state={state.className}
      aria-label="Synoptique hydraulique GeoCooling"
    >
      <header className="scada-v3-header">
        <div className="scada-v3-heading">
          <div className="scada-v3-heading__icon" aria-hidden="true">
            ◈
          </div>

          <div>
            <span className="scada-v3-eyebrow">
              PROCESS HYDRAULIQUE
            </span>

            <strong>
              Chaîne GeoCooling complète
            </strong>

            <small>{state.description}</small>
          </div>
        </div>

        <div className="scada-v3-header__right">
          <div
            className={`scada-v3-process-state ${state.className}`}
          >
            <span />
            <strong>{state.label}</strong>
          </div>

          <div className="scada-v3-legend">
            <span>
              <i className="is-source" />
              Source
            </span>

            <span>
              <i className="is-floor" />
              Départ
            </span>

            <span>
              <i className="is-return" />
              Retour
            </span>
          </div>
        </div>
      </header>

      <div className="scada-v3-canvas">
        <svg
          className="scada-v3-svg"
          viewBox="0 0 1260 590"
          role="img"
          aria-labelledby="scada-v3-title scada-v3-description"
        >
          <title id="scada-v3-title">
            Synoptique hydraulique GeoCooling
          </title>

          <desc id="scada-v3-description">
            Source géothermique, échangeur à plaques,
            électrovanne, ballon tampon, circulateur
            et plancher rafraîchissant.
          </desc>

          <defs>
            <filter
              id="scadaV3Glow"
              x="-40%"
              y="-40%"
              width="180%"
              height="180%"
            >
              <feGaussianBlur
                stdDeviation="5"
                result="blur"
              />

              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>

            <filter
              id="scadaV3Shadow"
              x="-40%"
              y="-40%"
              width="180%"
              height="180%"
            >
              <feDropShadow
                dx="0"
                dy="7"
                stdDeviation="8"
                floodColor="#020b14"
                floodOpacity="0.7"
              />
            </filter>

            <linearGradient
              id="scadaV3Tank"
              x1="0"
              y1="0"
              x2="0"
              y2="1"
            >
              <stop
                offset="0%"
                stopColor="#54d8ff"
                stopOpacity="0.75"
              />

              <stop
                offset="100%"
                stopColor="#1976a8"
                stopOpacity="0.32"
              />
            </linearGradient>

            <linearGradient
              id="scadaV3Equipment"
              x1="0"
              y1="0"
              x2="1"
              y2="1"
            >
              <stop
                offset="0%"
                stopColor="#132a42"
              />

              <stop
                offset="100%"
                stopColor="#071522"
              />
            </linearGradient>

            <marker
              id="scadaV3SourceArrow"
              markerWidth="10"
              markerHeight="10"
              refX="8"
              refY="3"
              orient="auto"
              markerUnits="strokeWidth"
            >
              <path
                d="M0,0 L0,6 L9,3 Z"
                className="scada-v3-arrow-source"
              />
            </marker>

            <marker
              id="scadaV3FloorArrow"
              markerWidth="10"
              markerHeight="10"
              refX="8"
              refY="3"
              orient="auto"
              markerUnits="strokeWidth"
            >
              <path
                d="M0,0 L0,6 L9,3 Z"
                className="scada-v3-arrow-floor"
              />
            </marker>

            <marker
              id="scadaV3ReturnArrow"
              markerWidth="10"
              markerHeight="10"
              refX="8"
              refY="3"
              orient="auto"
              markerUnits="strokeWidth"
            >
              <path
                d="M0,0 L0,6 L9,3 Z"
                className="scada-v3-arrow-return"
              />
            </marker>
          </defs>

          <g className="scada-v3-grid" aria-hidden="true">
            <path d="M40 80 H1220" />
            <path d="M40 160 H1220" />
            <path d="M40 240 H1220" />
            <path d="M40 320 H1220" />
            <path d="M40 400 H1220" />
            <path d="M40 480 H1220" />

            <path d="M120 40 V530" />
            <path d="M280 40 V530" />
            <path d="M440 40 V530" />
            <path d="M600 40 V530" />
            <path d="M760 40 V530" />
            <path d="M920 40 V530" />
            <path d="M1080 40 V530" />
          </g>

          <path
            className={sourceClass}
            markerEnd={
              sourceFlow
                ? "url(#scadaV3SourceArrow)"
                : undefined
            }
            d="M150 270 H270"
          />

          <path
            className={sourceClass}
            markerEnd={
              sourceFlow
                ? "url(#scadaV3SourceArrow)"
                : undefined
            }
            d="M420 270 H520"
          />

          <path
            className={sourceClass}
            markerEnd={
              sourceFlow
                ? "url(#scadaV3SourceArrow)"
                : undefined
            }
            d="M650 270 H750"
          />

          <path
            className={floorClass}
            markerEnd={
              floorFlow
                ? "url(#scadaV3FloorArrow)"
                : undefined
            }
            d="M890 270 H1020"
          />

          <path
            className={returnClass}
            markerEnd={
              floorFlow
                ? "url(#scadaV3ReturnArrow)"
                : undefined
            }
            d="M1140 410 H850 V370"
          />

          <path
            className={returnClass}
            markerEnd={
              floorFlow
                ? "url(#scadaV3ReturnArrow)"
                : undefined
            }
            d="M750 370 H660 V340"
          />

          <g
            className="scada-v3-equipment scada-v3-source"
            filter="url(#scadaV3Shadow)"
          >
            <rect
              x="30"
              y="180"
              width="120"
              height="180"
              rx="26"
            />

            <circle
              cx="90"
              cy="278"
              r="42"
              className="scada-v3-source-ring"
            />

            <path
              className="scada-v3-water"
              d="M55 270 C70 248 85 292 112 263"
            />

            <path
              className="scada-v3-water"
              d="M55 294 C70 272 85 316 112 287"
            />

            <text
              x="90"
              y="213"
              textAnchor="middle"
              className="scada-v3-label"
            >
              NAPPE
            </text>

            <text
              x="90"
              y="232"
              textAnchor="middle"
              className="scada-v3-sublabel"
            >
              SOURCE FROIDE
            </text>
          </g>

          <g
            className="scada-v3-equipment scada-v3-exchanger"
            filter="url(#scadaV3Shadow)"
          >
            <rect
              x="270"
              y="165"
              width="150"
              height="210"
              rx="25"
            />

            <path
              d="M305 215 L385 325"
              className="scada-v3-exchanger-line"
            />

            <path
              d="M385 215 L305 325"
              className="scada-v3-exchanger-line"
            />

            <path
              d="M320 205 V335"
              className="scada-v3-exchanger-plate"
            />

            <path
              d="M345 205 V335"
              className="scada-v3-exchanger-plate"
            />

            <path
              d="M370 205 V335"
              className="scada-v3-exchanger-plate"
            />

            <text
              x="345"
              y="194"
              textAnchor="middle"
              className="scada-v3-label"
            >
              ÉCHANGEUR
            </text>

            <text
              x="345"
              y="354"
              textAnchor="middle"
              className="scada-v3-sublabel"
            >
              À PLAQUES
            </text>
          </g>

          <g
            className={
              snapshot.valveOpen
                ? "scada-v3-valve is-open"
                : "scada-v3-valve is-closed"
            }
            filter="url(#scadaV3Shadow)"
          >
            <rect
              x="520"
              y="195"
              width="130"
              height="150"
              rx="23"
            />

            <path d="M552 252 L585 270 L552 288 Z" />
            <path d="M618 252 L585 270 L618 288 Z" />

            <line
              x1="585"
              y1="246"
              x2="585"
              y2="214"
            />

            <circle
              cx="585"
              cy="207"
              r="10"
            />

            <text
              x="585"
              y="323"
              textAnchor="middle"
              className="scada-v3-label"
            >
              VANNE
            </text>
          </g>

          <g
            className={
              floorFlow
                ? "scada-v3-equipment scada-v3-tank is-active"
                : "scada-v3-equipment scada-v3-tank"
            }
            filter="url(#scadaV3Shadow)"
          >
            <rect
              x="750"
              y="150"
              width="140"
              height="230"
              rx="34"
            />

            <path
              className="scada-v3-tank-level"
              d="M774 292 Q820 270 866 292 V350 H774 Z"
            />

            <line
              x1="774"
              y1="225"
              x2="866"
              y2="225"
              className="scada-v3-tank-divider"
            />

            <text
              x="820"
              y="183"
              textAnchor="middle"
              className="scada-v3-label"
            >
              BALLON
            </text>

            <text
              x="820"
              y="203"
              textAnchor="middle"
              className="scada-v3-sublabel"
            >
              TAMPON
            </text>
          </g>

          <g
            className={
              snapshot.pumpRunning
                ? "scada-v3-pump is-running"
                : "scada-v3-pump is-stopped"
            }
            filter="url(#scadaV3Shadow)"
          >
            <circle
              cx="955"
              cy="270"
              r="50"
            />

            <circle
              cx="955"
              cy="270"
              r="61"
              className="scada-v3-pump-halo"
            />

            <g className="scada-v3-pump-rotor">
              <path
                d="M955 235 C987 235 987 260 955 270 C923 280 923 305 955 305"
              />

              <path
                d="M920 270 C920 238 945 238 955 270 C965 302 990 302 990 270"
              />
            </g>

            <circle
              cx="955"
              cy="270"
              r="7"
              className="scada-v3-pump-center"
            />

            <text
              x="955"
              y="345"
              textAnchor="middle"
              className="scada-v3-label"
            >
              CIRCULATEUR
            </text>
          </g>

          <g
            className="scada-v3-equipment scada-v3-floor"
            filter="url(#scadaV3Shadow)"
          >
            <rect
              x="1020"
              y="155"
              width="215"
              height="255"
              rx="27"
            />

            <path
              className={
                floorFlow
                  ? "scada-v3-floor-loop is-active"
                  : "scada-v3-floor-loop"
              }
              d="M1050 220 H1205 V246 H1050 V272 H1205 V298 H1050 V324 H1205 V350 H1050"
            />

            <text
              x="1128"
              y="188"
              textAnchor="middle"
              className="scada-v3-label"
            >
              PLANCHER
            </text>

            <text
              x="1128"
              y="207"
              textAnchor="middle"
              className="scada-v3-sublabel"
            >
              RAFRAÎCHISSANT
            </text>
          </g>

          <g
            transform="translate(157 202)"
            className={sensorState(
              snapshot.sourceInTemperature,
            )}
          >
            <rect
              className="scada-v3-sensor"
              width="104"
              height="47"
              rx="11"
            />

            <text
              x="52"
              y="17"
              textAnchor="middle"
              className="scada-v3-sensor-label"
            >
              SOURCE ENTRÉE
            </text>

            <text
              x="52"
              y="35"
              textAnchor="middle"
              className="scada-v3-sensor-value"
            >
              {temperature(
                snapshot.sourceInTemperature,
              )}
            </text>
          </g>

          <g
            transform="translate(425 294)"
            className={sensorState(
              snapshot.sourceOutTemperature,
            )}
          >
            <rect
              className="scada-v3-sensor"
              width="104"
              height="47"
              rx="11"
            />

            <text
              x="52"
              y="17"
              textAnchor="middle"
              className="scada-v3-sensor-label"
            >
              SOURCE SORTIE
            </text>

            <text
              x="52"
              y="35"
              textAnchor="middle"
              className="scada-v3-sensor-value"
            >
              {temperature(
                snapshot.sourceOutTemperature,
              )}
            </text>
          </g>

          <g
            transform="translate(890 188)"
            className={sensorState(
              snapshot.supplyTemperature,
            )}
          >
            <rect
              className="scada-v3-sensor"
              width="116"
              height="47"
              rx="11"
            />

            <text
              x="58"
              y="17"
              textAnchor="middle"
              className="scada-v3-sensor-label"
            >
              DÉPART PLANCHER
            </text>

            <text
              x="58"
              y="35"
              textAnchor="middle"
              className="scada-v3-sensor-value"
            >
              {temperature(
                snapshot.supplyTemperature,
              )}
            </text>
          </g>

          <g
            transform="translate(1017 430)"
            className={sensorState(
              snapshot.returnTemperature,
            )}
          >
            <rect
              className="scada-v3-sensor"
              width="116"
              height="47"
              rx="11"
            />

            <text
              x="58"
              y="17"
              textAnchor="middle"
              className="scada-v3-sensor-label"
            >
              RETOUR PLANCHER
            </text>

            <text
              x="58"
              y="35"
              textAnchor="middle"
              className="scada-v3-sensor-value"
            >
              {temperature(
                snapshot.returnTemperature,
              )}
            </text>
          </g>

          <g transform="translate(290 420)">
            <rect
              width="130"
              height="58"
              rx="13"
              className="scada-v3-delta-box"
            />

            <text
              x="65"
              y="21"
              textAnchor="middle"
              className="scada-v3-delta-label"
            >
              ΔT SOURCE
            </text>

            <text
              x="65"
              y="43"
              textAnchor="middle"
              className="scada-v3-delta-value"
            >
              {deltaSource} °C
            </text>
          </g>

          <g transform="translate(750 420)">
            <rect
              width="140"
              height="58"
              rx="13"
              className="scada-v3-delta-box"
            />

            <text
              x="70"
              y="21"
              textAnchor="middle"
              className="scada-v3-delta-label"
            >
              ΔT PLANCHER
            </text>

            <text
              x="70"
              y="43"
              textAnchor="middle"
              className="scada-v3-delta-value"
            >
              {deltaFloor} °C
            </text>
          </g>
        </svg>
      </div>

      <footer className="scada-v3-footer">
        <article>
          <span>ÉLECTROVANNE</span>

          <strong
            className={
              snapshot.valveOpen
                ? "is-positive"
                : "is-neutral"
            }
          >
            {statusLabel(
              snapshot.valveOpen,
              "OUVERTE",
              "FERMÉE",
            )}
          </strong>
        </article>

        <article>
          <span>CIRCULATEUR</span>

          <strong
            className={
              snapshot.pumpRunning
                ? "is-positive"
                : "is-neutral"
            }
          >
            {statusLabel(
              snapshot.pumpRunning,
              "EN MARCHE",
              "À L’ARRÊT",
            )}
          </strong>
        </article>

        <article>
          <span>SÉCURITÉ</span>

          <strong
            className={
              snapshot.safetySafe === false
                ? "is-negative"
                : "is-positive"
            }
          >
            {statusLabel(
              snapshot.safetySafe,
              "VALIDÉE",
              "ALARME",
            )}
          </strong>
        </article>

        <article>
          <span>CONTRÔLEUR</span>

          <strong
            className={
              snapshot.deviceReady
                ? "is-positive"
                : "is-neutral"
            }
          >
            {statusLabel(
              snapshot.deviceReady,
              "PRÊT",
              "NON PRÊT",
            )}
          </strong>
        </article>

        <article>
          <span>ΔT PLANCHER</span>

          <strong
            className={
              deltaFloor === "--"
                ? "is-neutral"
                : "is-information"
            }
          >
            {deltaFloor} °C
          </strong>
        </article>
      </footer>
    </section>
  );
}
