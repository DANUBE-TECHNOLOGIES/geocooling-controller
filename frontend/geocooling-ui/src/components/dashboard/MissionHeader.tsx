import type { GeoCoolingSnapshot } from "@/types/geocooling";

type Props = {
  snapshot: GeoCoolingSnapshot;
};

type BadgeProps = {
  label: string;
  active: boolean | null;
};

function StatusBadge({ label, active }: BadgeProps) {
  const state =
    active === null ? "unknown" : active ? "online" : "offline";

  return (
    <div className={`mission-badge ${state}`}>
      <span className="mission-badge-dot" />
      <span>{label}</span>
    </div>
  );
}

export function MissionHeader({ snapshot }: Props) {
  const mode = snapshot.mode?.toUpperCase() ?? "--";

  const lastUpdate = new Date().toLocaleTimeString("fr-FR", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });

  return (
    <section className="mission-header">
      <div className="mission-left">
        <div className="mission-kicker">
          GEOCOOLING CONTROLLER
        </div>

        <h2 className="mission-title">
          Mission Control
        </h2>

        <div className="mission-mode">
          {mode}
        </div>
      </div>

      <div className="mission-right">
        <StatusBadge
          label="Brain"
          active={snapshot.deviceReady}
        />

        <StatusBadge
          label="Sécurité"
          active={snapshot.safetySafe}
        />

        <StatusBadge
          label="Pompe"
          active={snapshot.pumpRunning}
        />

        <StatusBadge
          label="Électrovanne"
          active={snapshot.valveOpen}
        />
      </div>

      <div className="mission-footer">
        Dernière mise à jour :
        <strong> {lastUpdate}</strong>
      </div>
    </section>
  );
}
