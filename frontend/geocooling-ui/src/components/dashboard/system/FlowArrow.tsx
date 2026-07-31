type FlowArrowProps = {
  active?: boolean;
  label?: string;
};

export default function FlowArrow({
  active = true,
  label,
}: FlowArrowProps) {
  return (
    <div
      className={`flow-arrow ${active ? "flow-arrow-active" : "flow-arrow-idle"}`}
      aria-label={label ?? (active ? "Flux actif" : "Flux arrêté")}
      title={label ?? (active ? "Flux actif" : "Flux arrêté")}
    >
      {label ? (
        <span className="flow-arrow-label">
          {label}
        </span>
      ) : null}
    </div>
  );
}
