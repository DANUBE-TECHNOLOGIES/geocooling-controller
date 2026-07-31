import { StatusBadge } from "@/components/ui/StatusBadge";

type TopBarProps = {
  connected: boolean;
  mode: string;
  refreshing: boolean;
  lastUpdate: Date | null;
  onRefresh: () => void;
};

function formatTime(date: Date | null): string {
  if (!date) {
    return "--:--:--";
  }

  return date.toLocaleTimeString("fr-FR", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function TopBar({
  connected,
  mode,
  refreshing,
  lastUpdate,
  onRefresh,
}: TopBarProps) {
  return (
    <header className="gc-topbar">
      <div className="gc-topbar__identity">
        <div className="gc-logo" aria-hidden="true">
          GC
        </div>

        <div>
          <p className="gc-topbar__eyebrow">SMART BUILDING CONTROLLER</p>
          <h1 className="gc-topbar__title">GeoCooling Enterprise</h1>
        </div>
      </div>

      <div className="gc-topbar__status">
        <StatusBadge
          label={connected ? "Contrôleur connecté" : "Contrôleur déconnecté"}
          tone={connected ? "success" : "danger"}
          pulse={connected}
        />

        <StatusBadge
          label={`Mode ${mode}`}
          tone={mode === "MANUAL" ? "warning" : "info"}
        />

        <div className="gc-topbar__update">
          <span>Dernière mise à jour</span>
          <strong>{formatTime(lastUpdate)}</strong>
        </div>

        <button
          className="gc-refresh-button"
          type="button"
          onClick={onRefresh}
          disabled={refreshing}
        >
          <span
            className={refreshing ? "gc-refresh-icon is-spinning" : "gc-refresh-icon"}
            aria-hidden="true"
          >
            ↻
          </span>

          {refreshing ? "Actualisation…" : "Actualiser"}
        </button>
      </div>
    </header>
  );
}
