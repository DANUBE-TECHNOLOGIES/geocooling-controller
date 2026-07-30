type MetricCardProps = {
  label: string;
  value: string | number;
  unit?: string;
  foot: string;
  state?: "on" | "off" | "warning";
  icon?: string;
  trend?: string;
};

export function MetricCard({
  label,
  value,
  unit,
  foot,
  state = "on",
  icon = "●",
  trend,
}: MetricCardProps) {
  return (
    <article className={`metric-card metric-${state}`}>
      <header className="metric-header">
        <div className="metric-icon">{icon}</div>

        <div className="metric-heading">
          <div className="metric-label">{label}</div>

          {trend ? (
            <div className="metric-trend">{trend}</div>
          ) : null}
        </div>
      </header>

      <section className="metric-main">
        <span className="metric-value">
          {value}
        </span>

        {unit ? (
          <span className="metric-unit">
            {unit}
          </span>
        ) : null}
      </section>

      <footer className="metric-foot">
        <span className={`state-dot ${state}`} />
        <span>{foot}</span>
      </footer>
    </article>
  );
}
