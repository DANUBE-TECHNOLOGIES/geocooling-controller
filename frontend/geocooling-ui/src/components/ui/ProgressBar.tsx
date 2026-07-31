type ProgressBarProps = {
  value: number | null | undefined;
  label: string;
};

function normalize(value: number | null | undefined): number {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return 0;
  }

  return Math.min(100, Math.max(0, value));
}

export function ProgressBar({ value, label }: ProgressBarProps) {
  const normalized = normalize(value);

  return (
    <div className="gc-progress">
      <div className="gc-progress__header">
        <span>{label}</span>
        <strong>{Math.round(normalized)} %</strong>
      </div>

      <div
        className="gc-progress__track"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(normalized)}
      >
        <div
          className="gc-progress__fill"
          style={{ width: `${normalized}%` }}
        />
      </div>
    </div>
  );
}
