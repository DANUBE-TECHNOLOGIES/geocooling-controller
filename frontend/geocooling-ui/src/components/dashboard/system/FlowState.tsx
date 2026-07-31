type FlowStateProps = {
  label: string;
  value: boolean | null;
  activeLabel?: string;
  inactiveLabel?: string;
  unknownLabel?: string;
};

export default function FlowState({
  label,
  value,
  activeLabel = "ON",
  inactiveLabel = "OFF",
  unknownLabel = "INCONNU",
}: FlowStateProps) {
  const stateClass =
    value === null
      ? "flow-state-unknown"
      : value
        ? "flow-state-on"
        : "flow-state-off";

  const stateLabel =
    value === null
      ? unknownLabel
      : value
        ? activeLabel
        : inactiveLabel;

  return (
    <div className="flow-state">
      <span>{label}</span>

      <span className={stateClass}>
        {stateLabel}
      </span>
    </div>
  );
}
