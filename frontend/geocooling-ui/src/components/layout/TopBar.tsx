"use client";

import {
  useEffect,
  useState,
} from "react";
import { usePathname } from "next/navigation";
import { StatusBadge } from "@/components/ui/StatusBadge";

type TopBarProps = {
  connected: boolean;
  mode: string;
  refreshing: boolean;
  lastUpdate: Date | null;
  generatedAt?: string | null;
  responseTime?: number;
  onRefresh: () => void;
};

type RouteDescriptor = {
  section: string;
  title: string;
  description: string;
  icon: string;
};

const routes: Record<string, RouteDescriptor> = {
  "/": {
    section: "SUPERVISION",
    title: "Dashboard",
    description: "Vue opérationnelle générale",
    icon: "▦",
  },
  "/brain": {
    section: "INTELLIGENCE",
    title: "GeoCooling Brain",
    description: "Décision, confiance et critères",
    icon: "◆",
  },
  "/alarms": {
    section: "SUPERVISION",
    title: "Alarmes",
    description: "Événements et diagnostics actifs",
    icon: "!",
  },
  "/historian": {
    section: "ANALYSE",
    title: "Historian",
    description: "Courbes, tendances et export",
    icon: "⌁",
  },
  "/forecast": {
    section: "ANALYSE",
    title: "Prévisions",
    description: "Projection thermique locale",
    icon: "↗",
  },
  "/digital-twin": {
    section: "SIMULATION",
    title: "Digital Twin",
    description: "Jumeau numérique interactif",
    icon: "◇",
  },
  "/hardware": {
    section: "TECHNIQUE",
    title: "Hardware",
    description: "Matériel, actionneurs et sondes",
    icon: "◉",
  },
  "/runtime": {
    section: "TECHNIQUE",
    title: "Runtime",
    description: "Services, API et observabilité",
    icon: "⚙",
  },
};

function routeDescriptor(
  pathname: string,
): RouteDescriptor {
  if (routes[pathname]) {
    return routes[pathname];
  }

  const matchingRoute = Object.keys(routes)
    .filter((route) => route !== "/")
    .find((route) =>
      pathname.startsWith(`${route}/`),
    );

  return matchingRoute
    ? routes[matchingRoute]
    : {
        section: "GEOCOOLING",
        title: "Supervision",
        description: "Smart Building Controller",
        icon: "GC",
      };
}

function formatTime(
  date: Date | null,
): string {
  if (!date) {
    return "--:--:--";
  }

  return date.toLocaleTimeString("fr-FR", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function formatClock(
  date: Date | null,
): string {
  if (!date) {
    return "--:--";
  }

  return date.toLocaleTimeString("fr-FR", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatDate(
  date: Date | null,
): string {
  if (!date) {
    return "Date indisponible";
  }

  return date.toLocaleDateString("fr-FR", {
    weekday: "short",
    day: "2-digit",
    month: "short",
  });
}

function normalizeMode(mode: string): {
  label: string;
  tone: "success" | "warning" | "info" | "neutral";
} {
  switch (mode.trim().toLowerCase()) {
    case "automatic":
    case "automatique":
      return {
        label: "AUTOMATIQUE",
        tone: "success",
      };

    case "manual":
    case "manuel":
      return {
        label: "MANUEL",
        tone: "warning",
      };

    case "simulation":
      return {
        label: "SIMULATION",
        tone: "info",
      };

    default:
      return {
        label: "INCONNU",
        tone: "neutral",
      };
  }
}

function latencyState(
  responseTime: number,
): {
  label: string;
  className: string;
  description: string;
} {
  if (responseTime <= 0) {
    return {
      label: "-- ms",
      className: "is-neutral",
      description: "Latence inconnue",
    };
  }

  if (responseTime < 500) {
    return {
      label: `${responseTime} ms`,
      className: "is-good",
      description: "Réponse rapide",
    };
  }

  if (responseTime < 1500) {
    return {
      label: `${responseTime} ms`,
      className: "is-warning",
      description: "Réponse acceptable",
    };
  }

  return {
    label: `${responseTime} ms`,
    className: "is-critical",
    description: "Latence élevée",
  };
}

function snapshotState(
  generatedAt: string | null | undefined,
  lastUpdate: Date | null,
): {
  label: string;
  className: string;
  description: string;
} {
  if (!generatedAt || !lastUpdate) {
    return {
      label: "INCONNU",
      className: "is-neutral",
      description: "Horodatage indisponible",
    };
  }

  const generated = new Date(generatedAt);

  if (Number.isNaN(generated.getTime())) {
    return {
      label: "INVALIDE",
      className: "is-critical",
      description: "Horodatage incorrect",
    };
  }

  const ageSeconds = Math.max(
    0,
    Math.round(
      (
        lastUpdate.getTime() -
        generated.getTime()
      ) / 1000,
    ),
  );

  if (ageSeconds <= 15) {
    return {
      label: `${ageSeconds} s`,
      className: "is-good",
      description: "Données récentes",
    };
  }

  if (ageSeconds <= 60) {
    return {
      label: `${ageSeconds} s`,
      className: "is-warning",
      description: "Données retardées",
    };
  }

  return {
    label: `${ageSeconds} s`,
    className: "is-critical",
    description: "Données anciennes",
  };
}

export function TopBar({
  connected,
  mode,
  refreshing,
  lastUpdate,
  generatedAt = null,
  responseTime = 0,
  onRefresh,
}: TopBarProps) {
  const pathname = usePathname();

  const [currentTime, setCurrentTime] =
    useState<Date | null>(null);

  useEffect(() => {
    setCurrentTime(new Date());

    const timer = window.setInterval(() => {
      setCurrentTime(new Date());
    }, 1_000);

    return () => {
      window.clearInterval(timer);
    };
  }, []);

  const route = routeDescriptor(pathname);
  const normalizedMode = normalizeMode(mode);
  const latency = latencyState(responseTime);

  const snapshot = snapshotState(
    generatedAt,
    lastUpdate,
  );

  return (
    <header className="gc-command-header">
      <div className="gc-command-header__page">
        <div
          className="gc-command-header__page-icon"
          aria-hidden="true"
        >
          {route.icon}
        </div>

        <div className="gc-command-header__page-content">
          <div className="gc-command-header__breadcrumb">
            <span>
              SMART BUILDING CONTROLLER
            </span>

            <i aria-hidden="true">/</i>

            <strong>{route.section}</strong>
          </div>

          <div className="gc-command-header__title-row">
            <h1>{route.title}</h1>

            <span>
              {route.description}
            </span>
          </div>
        </div>
      </div>

      <div className="gc-command-header__supervision">
        <article className="gc-command-header__metric">
          <span>CONTRÔLEUR</span>

          <StatusBadge
            label={
              connected
                ? "CONNECTÉ"
                : "HORS LIGNE"
            }
            tone={
              connected
                ? "success"
                : "danger"
            }
            pulse={connected}
          />
        </article>

        <article className="gc-command-header__metric">
          <span>MODE</span>

          <StatusBadge
            label={normalizedMode.label}
            tone={normalizedMode.tone}
          />
        </article>

        <article className="gc-command-header__metric">
          <span>LATENCE</span>

          <strong
            className={latency.className}
            title={latency.description}
          >
            {latency.label}
          </strong>
        </article>

        <article className="gc-command-header__metric">
          <span>SNAPSHOT</span>

          <strong
            className={snapshot.className}
            title={snapshot.description}
          >
            {snapshot.label}
          </strong>
        </article>

        <article className="gc-command-header__sync">
          <span>DERNIÈRE SYNC</span>

          <strong>
            {formatTime(lastUpdate)}
          </strong>
        </article>

        <div className="gc-command-header__clock">
          <span>
            {formatDate(currentTime)}
          </span>

          <strong>
            {formatClock(currentTime)}
          </strong>
        </div>

        <button
          className="gc-command-header__refresh"
          type="button"
          onClick={onRefresh}
          disabled={refreshing}
          aria-label="Actualiser les données GeoCooling"
          title="Actualiser les données"
        >
          <span
            className={
              refreshing
                ? "is-spinning"
                : ""
            }
            aria-hidden="true"
          >
            ↻
          </span>

          <strong>
            {refreshing
              ? "SYNC"
              : "ACTUALISER"}
          </strong>
        </button>
      </div>
    </header>
  );
}
