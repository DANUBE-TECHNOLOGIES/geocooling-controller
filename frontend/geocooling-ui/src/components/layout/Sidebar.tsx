const nav = [
  ["▦", "Dashboard", true],
  ["◇", "Digital Twin", false],
  ["⌁", "Historique", false],
  ["⚙", "Maintenance", false],
  ["≡", "Réglages", false],
] as const;

export function Sidebar() {
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark">GC</div>
        <div>
          <div className="brand-name">GeoCooling</div>
          <span className="brand-subtitle">Enterprise Controller</span>
        </div>
      </div>

      <div className="nav-title">Pilotage</div>
      <nav className="nav">
        {nav.map(([icon, label, active]) => (
          <a className={`nav-item ${active ? "active" : ""}`} href="#" key={label}>
            <span className="nav-icon">{icon}</span>
            {label}
          </a>
        ))}
      </nav>

      <div className="sidebar-footer">
        <strong>Brain V2 disponible</strong>
        Mode sécurisé · Simulation active
      </div>
    </aside>
  );
}
