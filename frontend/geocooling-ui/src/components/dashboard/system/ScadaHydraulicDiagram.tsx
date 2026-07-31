import type { GeoCoolingSnapshot } from "@/types/geocooling";

type Props = {
  snapshot: GeoCoolingSnapshot;
};

function temp(value: number | null): string {
  return value === null ? "--.- °C" : `${value.toFixed(1)} °C`;
}

export default function ScadaHydraulicDiagram({
  snapshot,
}: Props) {
  const flowActive =
    snapshot.pumpRunning &&
    snapshot.valveOpen &&
    snapshot.safetySafe !== false;

  return (
    <div className="scada-diagram-shell">
      <svg
        className="scada-diagram"
        viewBox="0 0 1000 420"
        role="img"
        aria-label="Synoptique hydraulique GeoCooling"
      >
        <defs>
          <linearGradient
            id="pipeGradient"
            x1="0"
            y1="0"
            x2="1"
            y2="0"
          >
            <stop offset="0%" stopColor="#2575a8" />
            <stop offset="55%" stopColor="#42d3b5" />
            <stop offset="100%" stopColor="#52a7d8" />
          </linearGradient>

          <filter id="glow">
            <feGaussianBlur stdDeviation="4" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>

          <marker
            id="arrowHead"
            markerWidth="10"
            markerHeight="10"
            refX="8"
            refY="5"
            orient="auto"
          >
            <path
              d="M0,0 L10,5 L0,10 Z"
              fill="#42d3b5"
            />
          </marker>
        </defs>

        <rect
          x="20"
          y="20"
          width="960"
          height="380"
          rx="24"
          className="scada-background"
        />

        <path
          d="M160 205 H295"
          className={`scada-pipe ${
            flowActive ? "scada-pipe-active" : ""
          }`}
          markerEnd="url(#arrowHead)"
        />

        <path
          d="M425 205 H560"
          className={`scada-pipe ${
            flowActive ? "scada-pipe-active" : ""
          }`}
          markerEnd="url(#arrowHead)"
        />

        <path
          d="M690 205 H825"
          className={`scada-pipe ${
            flowActive ? "scada-pipe-active" : ""
          }`}
          markerEnd="url(#arrowHead)"
        />

        <g transform="translate(70 135)">
          <rect
            width="120"
            height="140"
            rx="18"
            className="scada-unit"
          />
          <circle
            cx="60"
            cy="48"
            r="27"
            className="scada-source-icon"
          />
          <path
            d="M48 50 C48 37 60 27 60 27 C60 27 72 37 72 50 C72 62 66 69 60 69 C54 69 48 62 48 50Z"
            className="scada-water-drop"
          />
          <text
            x="60"
            y="96"
            textAnchor="middle"
            className="scada-unit-title"
          >
            NAPPE
          </text>
          <text
            x="60"
            y="119"
            textAnchor="middle"
            className="scada-unit-value"
          >
            {temp(snapshot.sourceInTemperature)}
          </text>
        </g>

        <g transform="translate(305 135)">
          <rect
            width="120"
            height="140"
            rx="18"
            className="scada-unit"
          />
          <rect
            x="36"
            y="25"
            width="48"
            height="50"
            rx="8"
            className="scada-exchanger"
          />
          <path
            d="M44 37 H76 M44 49 H76 M44 61 H76"
            className="scada-exchanger-lines"
          />
          <text
            x="60"
            y="96"
            textAnchor="middle"
            className="scada-unit-title"
          >
            ÉCHANGEUR
          </text>
          <text
            x="60"
            y="119"
            textAnchor="middle"
            className="scada-unit-value"
          >
            {temp(snapshot.sourceOutTemperature)}
          </text>
        </g>

        <g transform="translate(570 135)">
          <rect
            width="120"
            height="140"
            rx="18"
            className="scada-unit"
          />
          <circle
            cx="60"
            cy="50"
            r="28"
            className={
              snapshot.pumpRunning
                ? "scada-pump scada-pump-running"
                : "scada-pump"
            }
          />
          <path
            d="M60 31 L73 55 L47 55 Z"
            className="scada-pump-blade"
          />
          <text
            x="60"
            y="96"
            textAnchor="middle"
            className="scada-unit-title"
          >
            POMPE
          </text>
          <text
            x="60"
            y="119"
            textAnchor="middle"
            className="scada-unit-value"
          >
            {snapshot.pumpRunning ? "MARCHE" : "ARRÊT"}
          </text>
        </g>

        <g transform="translate(835 135)">
          <rect
            width="120"
            height="140"
            rx="18"
            className="scada-unit"
          />
          <path
            d="M32 35 H88 V68 H32 Z"
            className="scada-floor"
          />
          <path
            d="M38 43 H82 M38 53 H82 M38 63 H82"
            className="scada-floor-lines"
          />
          <text
            x="60"
            y="96"
            textAnchor="middle"
            className="scada-unit-title"
          >
            PLANCHER
          </text>
          <text
            x="60"
            y="119"
            textAnchor="middle"
            className="scada-unit-value"
          >
            {temp(snapshot.supplyTemperature)}
          </text>
        </g>

        <g transform="translate(420 315)">
          <rect
            width="160"
            height="48"
            rx="12"
            className={
              snapshot.valveOpen
                ? "scada-status-box scada-status-ok"
                : "scada-status-box"
            }
          />
          <text
            x="80"
            y="30"
            textAnchor="middle"
            className="scada-status-text"
          >
            VANNE {snapshot.valveOpen ? "OUVERTE" : "FERMÉE"}
          </text>
        </g>
      </svg>
    </div>
  );
}
