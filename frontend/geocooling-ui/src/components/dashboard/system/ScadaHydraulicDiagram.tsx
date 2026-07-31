import type { GeoCoolingSnapshot } from "@/types/geocooling";

type Props = {
  snapshot: GeoCoolingSnapshot;
};

function temperature(value: number | null): string {
  return value === null ? "--.- °C" : `${value.toFixed(1)} °C`;
}

function statusLabel(value: boolean | null, active: string, inactive: string): string {
  if (value === null) return "INCONNU";
  return value ? active : inactive;
}

export default function ScadaHydraulicDiagram({ snapshot }: Props) {
  const safe = snapshot.safetySafe !== false;
  const sourceFlow = snapshot.valveOpen && safe;
  const floorFlow = snapshot.pumpRunning && snapshot.valveOpen && safe;
  const fault = snapshot.safetySafe === false;

  const sourceClass = sourceFlow
    ? "scada-v2-pipe scada-v2-pipe-source scada-v2-flow"
    : "scada-v2-pipe scada-v2-pipe-idle";

  const floorClass = floorFlow
    ? "scada-v2-pipe scada-v2-pipe-floor scada-v2-flow"
    : "scada-v2-pipe scada-v2-pipe-idle";

  return (
    <section
      className={`scada-v2 ${fault ? "scada-v2-fault" : ""}`}
      aria-label="Synoptique hydraulique GeoCooling"
    >
      <div className="scada-v2-topbar">
        <div>
          <span className="scada-v2-eyebrow">SCHÉMA DE PROCESS</span>
          <strong>Chaîne hydraulique complète</strong>
        </div>

        <div className="scada-v2-legend" aria-label="Légende">
          <span><i className="scada-v2-dot scada-v2-dot-source" /> Source</span>
          <span><i className="scada-v2-dot scada-v2-dot-floor" /> Plancher</span>
          <span><i className="scada-v2-dot scada-v2-dot-idle" /> Inactif</span>
        </div>
      </div>

      <div className="scada-v2-canvas">
        <svg
          className="scada-v2-svg"
          viewBox="0 0 1180 500"
          role="img"
          aria-labelledby="scada-v2-title scada-v2-desc"
        >
          <title id="scada-v2-title">Circuit hydraulique GeoCooling</title>
          <desc id="scada-v2-desc">
            Nappe, échangeur, électrovanne, ballon tampon, circulateur et plancher.
          </desc>

          <defs>
            <filter id="scadaGlow" x="-30%" y="-30%" width="160%" height="160%">
              <feGaussianBlur stdDeviation="4" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
            <marker
              id="scadaArrowSource"
              markerWidth="10"
              markerHeight="10"
              refX="8"
              refY="3"
              orient="auto"
              markerUnits="strokeWidth"
            >
              <path d="M0,0 L0,6 L9,3 z" className="scada-v2-arrow-source" />
            </marker>
            <marker
              id="scadaArrowFloor"
              markerWidth="10"
              markerHeight="10"
              refX="8"
              refY="3"
              orient="auto"
              markerUnits="strokeWidth"
            >
              <path d="M0,0 L0,6 L9,3 z" className="scada-v2-arrow-floor" />
            </marker>
          </defs>

          <path
            className={sourceClass}
            markerEnd={sourceFlow ? "url(#scadaArrowSource)" : undefined}
            d="M130 250 H260"
          />
          <path
            className={sourceClass}
            markerEnd={sourceFlow ? "url(#scadaArrowSource)" : undefined}
            d="M390 250 H500"
          />
          <path
            className={sourceClass}
            markerEnd={sourceFlow ? "url(#scadaArrowSource)" : undefined}
            d="M610 250 H720"
          />
          <path
            className={floorClass}
            markerEnd={floorFlow ? "url(#scadaArrowFloor)" : undefined}
            d="M850 250 H950"
          />

          <g className="scada-v2-equipment">
            <rect x="20" y="170" width="110" height="160" rx="24" />
            <path className="scada-v2-water" d="M45 270 C62 245 78 292 102 260" />
            <path className="scada-v2-water" d="M45 292 C62 267 78 314 102 282" />
            <text x="75" y="205" textAnchor="middle" className="scada-v2-label">NAPPE</text>
            <text x="75" y="225" textAnchor="middle" className="scada-v2-sublabel">SOURCE</text>
          </g>

          <g className="scada-v2-equipment">
            <rect x="260" y="160" width="130" height="180" rx="24" />
            <path className="scada-v2-exchanger" d="M292 205 L358 295 M358 205 L292 295" />
            <text x="325" y="190" textAnchor="middle" className="scada-v2-label">ÉCHANGEUR</text>
            <text x="325" y="317" textAnchor="middle" className="scada-v2-sublabel">PLAQUES</text>
          </g>

          <g className={`scada-v2-valve ${snapshot.valveOpen ? "is-open" : "is-closed"}`}>
            <rect x="500" y="185" width="110" height="130" rx="22" />
            <path d="M530 235 L555 250 L530 265 Z" />
            <path d="M580 235 L555 250 L580 265 Z" />
            <line x1="555" y1="220" x2="555" y2="190" />
            <circle cx="555" cy="183" r="10" />
            <text x="555" y="295" textAnchor="middle" className="scada-v2-label">VANNE</text>
          </g>

          <g className="scada-v2-equipment">
            <rect x="720" y="155" width="130" height="190" rx="28" />
            <path className="scada-v2-tank-level" d="M740 275 Q785 250 830 275 V320 H740 Z" />
            <line x1="738" y1="220" x2="832" y2="220" />
            <text x="785" y="188" textAnchor="middle" className="scada-v2-label">BALLON</text>
            <text x="785" y="208" textAnchor="middle" className="scada-v2-sublabel">TAMPON</text>
          </g>

          <g className={`scada-v2-pump ${snapshot.pumpRunning ? "is-running" : "is-stopped"}`}>
            <circle cx="900" cy="250" r="46" />
            <path className="scada-v2-pump-rotor" d="M900 218 C927 218 927 242 900 250 C873 258 873 282 900 282" />
            <circle cx="900" cy="250" r="7" />
            <text x="900" y="320" textAnchor="middle" className="scada-v2-label">POMPE</text>
          </g>

          <g className="scada-v2-equipment">
            <rect x="950" y="160" width="210" height="180" rx="26" />
            <path className="scada-v2-floor-loop" d="M978 215 H1132 V238 H978 V261 H1132 V284 H978" />
            <text x="1055" y="195" textAnchor="middle" className="scada-v2-label">PLANCHER</text>
            <text x="1055" y="318" textAnchor="middle" className="scada-v2-sublabel">RAFRAÎCHISSANT</text>
          </g>

          <g transform="translate(145 192)">
            <rect className="scada-v2-temp-box" width="98" height="42" rx="10" />
            <text x="49" y="17" textAnchor="middle" className="scada-v2-temp-label">ENTRÉE</text>
            <text x="49" y="33" textAnchor="middle" className="scada-v2-temp-value">
              {temperature(snapshot.sourceInTemperature)}
            </text>
          </g>

          <g transform="translate(395 266)">
            <rect className="scada-v2-temp-box" width="98" height="42" rx="10" />
            <text x="49" y="17" textAnchor="middle" className="scada-v2-temp-label">SORTIE</text>
            <text x="49" y="33" textAnchor="middle" className="scada-v2-temp-value">
              {temperature(snapshot.sourceOutTemperature)}
            </text>
          </g>

          <g transform="translate(850 165)">
            <rect className="scada-v2-temp-box" width="98" height="42" rx="10" />
            <text x="49" y="17" textAnchor="middle" className="scada-v2-temp-label">DÉPART</text>
            <text x="49" y="33" textAnchor="middle" className="scada-v2-temp-value">
              {temperature(snapshot.supplyTemperature)}
            </text>
          </g>

          <g transform="translate(1030 355)">
            <rect className="scada-v2-temp-box" width="110" height="42" rx="10" />
            <text x="55" y="17" textAnchor="middle" className="scada-v2-temp-label">RETOUR</text>
            <text x="55" y="33" textAnchor="middle" className="scada-v2-temp-value">
              {temperature(snapshot.returnTemperature)}
            </text>
          </g>
        </svg>
      </div>

      <div className="scada-v2-equipment-strip">
        <div className="scada-v2-state-card">
          <span>ÉLECTROVANNE</span>
          <strong className={snapshot.valveOpen ? "is-positive" : "is-neutral"}>
            {statusLabel(snapshot.valveOpen, "OUVERTE", "FERMÉE")}
          </strong>
        </div>

        <div className="scada-v2-state-card">
          <span>CIRCULATEUR</span>
          <strong className={snapshot.pumpRunning ? "is-positive" : "is-neutral"}>
            {statusLabel(snapshot.pumpRunning, "EN MARCHE", "À L’ARRÊT")}
          </strong>
        </div>

        <div className="scada-v2-state-card">
          <span>SÉCURITÉ</span>
          <strong className={snapshot.safetySafe === false ? "is-negative" : "is-positive"}>
            {statusLabel(snapshot.safetySafe, "VALIDÉE", "ALARME")}
          </strong>
        </div>

        <div className="scada-v2-state-card">
          <span>CONTRÔLEUR</span>
          <strong className={snapshot.deviceReady ? "is-positive" : "is-neutral"}>
            {statusLabel(snapshot.deviceReady, "PRÊT", "NON PRÊT")}
          </strong>
        </div>
      </div>
    </section>
  );
}
