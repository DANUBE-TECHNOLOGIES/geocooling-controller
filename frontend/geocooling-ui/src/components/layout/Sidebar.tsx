"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

type SidebarProps = {
  connected: boolean;
  mode: string;
};

type NavigationItem = {
  href: string;
  label: string;
  description: string;
  icon: string;
};

type NavigationGroup = {
  label: string;
  items: NavigationItem[];
};

const navigation: NavigationGroup[] = [
  {
    label: "SUPERVISION",
    items: [
      {
        href: "/",
        label: "Dashboard",
        description: "Vue générale",
        icon: "▦",
      },
      {
        href: "/brain",
        label: "Brain",
        description: "Décision & confiance",
        icon: "◆",
      },
      {
        href: "/alarms",
        label: "Alarmes",
        description: "Événements actifs",
        icon: "!",
      },
    ],
  },
  {
    label: "ANALYSE",
    items: [
      {
        href: "/historian",
        label: "Historian",
        description: "Courbes & export",
        icon: "⌁",
      },
      {
        href: "/forecast",
        label: "Prévisions",
        description: "Projection thermique",
        icon: "↗",
      },
      {
        href: "/digital-twin",
        label: "Digital Twin",
        description: "Simulation locale",
        icon: "◇",
      },
    ],
  },
  {
    label: "TECHNIQUE",
    items: [
      {
        href: "/hardware",
        label: "Hardware",
        description: "Matériel & sondes",
        icon: "◉",
      },
      {
        href: "/telemetry",
        label: "Télémétrie",
        description: "ESPHome & MQTT",
        icon: "≋",
      },
      {
        href: "/commissioning",
        label: "Commissioning",
        description: "Gates de mise en service",
        icon: "✓",
      },
      {
        href: "/runtime",
        label: "Runtime",
        description: "Services & API",
        icon: "⚙",
      },
    ],
  },
];

function isActive(
  pathname: string,
  href: string,
): boolean {
  if (href === "/") {
    return pathname === "/";
  }

  return (
    pathname === href ||
    pathname.startsWith(`${href}/`)
  );
}

function normalizeMode(mode: string): string {
  switch (mode.trim().toLowerCase()) {
    case "automatic":
    case "automatique":
      return "AUTOMATIQUE";

    case "manual":
    case "manuel":
      return "MANUEL";

    case "simulation":
      return "SIMULATION";

    default:
      return "INCONNU";
  }
}

export function Sidebar({
  connected,
  mode,
}: SidebarProps) {
  const pathname = usePathname();

  return (
    <aside className="gc-sidebar">
      <div className="gc-sidebar__brand">
        <div
          className="gc-sidebar__logo"
          aria-hidden="true"
        >
          GC
        </div>

        <div>
          <strong>GeoCooling</strong>
          <span>Enterprise Control</span>
        </div>
      </div>

      <nav
        className="gc-sidebar__navigation"
        aria-label="Navigation principale"
      >
        {navigation.map((group) => (
          <section
            key={group.label}
            className="gc-sidebar__group"
          >
            <h2>{group.label}</h2>

            <div>
              {group.items.map((item) => {
                const active = isActive(
                  pathname,
                  item.href,
                );

                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={
                      active
                        ? "gc-sidebar-link is-active"
                        : "gc-sidebar-link"
                    }
                    aria-current={
                      active ? "page" : undefined
                    }
                  >
                    <span
                      className="gc-sidebar-link__icon"
                      aria-hidden="true"
                    >
                      {item.icon}
                    </span>

                    <span className="gc-sidebar-link__content">
                      <strong>{item.label}</strong>
                      <small>
                        {item.description}
                      </small>
                    </span>

                    <span
                      className="gc-sidebar-link__arrow"
                      aria-hidden="true"
                    >
                      ›
                    </span>
                  </Link>
                );
              })}
            </div>
          </section>
        ))}
      </nav>

      <footer className="gc-sidebar__footer">
        <div className="gc-sidebar__status">
          <span
            className={
              connected
                ? "is-connected"
                : "is-disconnected"
            }
          />

          <div>
            <strong>
              {connected
                ? "Contrôleur connecté"
                : "Contrôleur hors ligne"}
            </strong>

            <small>
              Mode {normalizeMode(mode)}
            </small>
          </div>
        </div>

        <div className="gc-sidebar__version">
          <span>SMART BUILDING CONTROLLER</span>
          <strong>UI Enterprise 1.0</strong>
        </div>
      </footer>
    </aside>
  );
}
