export function Topbar() {
  return (
    <header className="topbar">
      <div className="topbar-left">
        <span>⌂</span>
        <span>Installation principale</span>
      </div>
      <div className="topbar-right">
        <div className="status-chip">Backend <strong>À connecter</strong></div>
        <div className="status-chip">Mode <strong>Simulation</strong></div>
      </div>
    </header>
  );
}
