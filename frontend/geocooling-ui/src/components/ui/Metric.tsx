type MetricTone =
  | "default"
  | "success"
  | "warning"
  | "danger"
  | "info";

type MetricProps = {
  label: string;
  value: string;
  unit?: string;
  note?: string;
  tone?: MetricTone;
};

export function Metric({
  label,
  value,
  unit,
  note,
  tone = "default",
}: MetricProps) {
  return (
    <div className={`gc-metric gc-metric--${tone}`}>
      <span className="gc-metric__label">{label}</span>

      <div className="gc-metric__value-row">
        <strong className="gc-metric__value">{value}</strong>

        {unit ? <span className="gc-metric__unit">{unit}</span> : null}
      </div>

      {note ? <span className="gc-metric__note">{note}</span> : null}
    </div>
  );
}
