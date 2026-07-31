type TemperatureBadgeProps = {
  label: string;
  value: number | null;
  unit?: string;
};

export default function TemperatureBadge({
  label,
  value,
  unit = "°C",
}: TemperatureBadgeProps) {
  const display =
    value === null
      ? "--"
      : value.toFixed(1);

  return (
    <div className="temperature-badge">

      <div className="temperature-badge-label">
        {label}
      </div>

      <div className="temperature-badge-value">
        {display}
        <span className="temperature-badge-unit">
          {unit}
        </span>
      </div>

    </div>
  );
}
