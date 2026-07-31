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

  const status =
    state === "on"
      ? "ONLINE"
      : state === "warning"
      ? "SURVEILLANCE"
      : "OFFLINE";

  return (
    <article className={`metric-card metric-${state}`}>

      <header className="metric-header">

        <div className="metric-icon-wrapper">

          <div className="metric-icon">
            {icon}
          </div>

        </div>

        <div className="metric-heading">

          <div className="metric-label">
            {label}
          </div>

          {trend && (
            <div className="metric-trend">
              {trend}
            </div>
          )}

        </div>

        <div className={`metric-status ${state}`}>
          {status}
        </div>

      </header>

      <section className="metric-main">

        <span className="metric-value">
          {value}
        </span>

        {unit && (
          <span className="metric-unit">
            {unit}
          </span>
        )}

      </section>

      <footer className="metric-foot">

        <span className={`state-dot ${state}`} />

        <span className="metric-foot-text">
          {foot}
        </span>

      </footer>

    </article>
  );
}
