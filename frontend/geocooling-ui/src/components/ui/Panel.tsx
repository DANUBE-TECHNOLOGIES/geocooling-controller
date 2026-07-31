import type { ReactNode } from "react";

type PanelProps = {
  title: string;
  subtitle?: string;
  icon?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
};

export function Panel({
  title,
  subtitle,
  icon,
  action,
  children,
  className = "",
}: PanelProps) {
  return (
    <section className={`gc-panel ${className}`}>
      <header className="gc-panel__header">
        <div className="gc-panel__heading">
          {icon ? (
            <span className="gc-panel__icon" aria-hidden="true">
              {icon}
            </span>
          ) : null}

          <div>
            <h2 className="gc-panel__title">{title}</h2>

            {subtitle ? (
              <p className="gc-panel__subtitle">{subtitle}</p>
            ) : null}
          </div>
        </div>

        {action ? <div className="gc-panel__action">{action}</div> : null}
      </header>

      <div className="gc-panel__body">{children}</div>
    </section>
  );
}
