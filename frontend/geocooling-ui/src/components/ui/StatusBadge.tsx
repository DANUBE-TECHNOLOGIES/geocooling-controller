type StatusTone =
  | "success"
  | "warning"
  | "danger"
  | "neutral"
  | "info";

type StatusBadgeProps = {
  label: string;
  tone?: StatusTone;
  pulse?: boolean;
};

export function StatusBadge({
  label,
  tone = "neutral",
  pulse = false,
}: StatusBadgeProps) {
  return (
    <span className={`gc-badge gc-badge--${tone}`}>
      {pulse ? (
        <span className="gc-badge__pulse" aria-hidden="true" />
      ) : null}

      <span>{label}</span>
    </span>
  );
}
