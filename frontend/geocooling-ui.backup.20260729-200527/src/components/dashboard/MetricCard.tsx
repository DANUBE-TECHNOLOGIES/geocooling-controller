type MetricCardProps = {
  label: string;
  value: string | number;
  unit?: string;
  foot: string;
  state?: "on" | "off" | "warning";
};

export function MetricCard({
  label,
  value,
  unit,
  foot,
  state = "on",
}: MetricCardProps) {
  return (
    <article className="metric-card">
      <div className="metric-label">{label}</div>
      <div className="metric-value">
        {value}
        {unit ? <span className="metric-unit">{unit}</span> : null}
      </div>
      <div className="metric-foot">
        <span className={`state-dot ${state}`} />
        {foot}
      </div>
    </article>
  );
}
