type Props = {
  title: string;
  value: string;
};

export default function EquipmentCard({
  title,
  value,
}: Props) {
  return (
    <div className="equipment">

      <div className="equipment-title">
        {title}
      </div>

      <div className="equipment-value">
        {value}
      </div>

    </div>
  );
}
