import type {
  GeoCoolingMode,
  GeoCoolingSnapshot,
} from "@/types/geocooling";
import { Panel } from "@/components/ui/Panel";
import { StatusBadge } from "@/components/ui/StatusBadge";

type ControllerStatusCardProps = {
  snapshot: GeoCoolingSnapshot | null;
  connected: boolean;
};

type ControllerState = {
  label: string;
  tone: "success" | "warning" | "danger" | "neutral";
  className: string;
  description: string;
};

type ReadinessCheck = {
  label: string;
  detail: string;
  valid: boolean;
  warning?: boolean;
};

function normalizeMode(
  mode: GeoCoolingMode | undefined,
): {
  label: string;
  className: string;
  description: string;
} {
  switch (mode) {
    case "automatic":
      return {
        label: "AUTOMATIQUE",
        className: "is-good",
        description:
          "Le Brain pilote automatiquement la stratégie GeoCooling.",
      };

    case "manual":
      return {
        label: "MANUEL",
        className: "is-warning",
        description:
          "Le pilotage automatique n’est pas prioritaire.",
      };

    case "simulation":
      return {
        label: "SIMULATION",
        className: "is-information",
        description:
          "Les décisions sont évaluées sans commande physique réelle.",
      };

    default:
      return {
        label: "INCONNU",
        className: "is-neutral",
        description:
          "Le mode courant n’a pas été transmis par le contrôleur.",
      };
  }
}

function controllerState(
  snapshot: GeoCoolingSnapshot | null,
  connected: boolean,
): ControllerState {
  if (!connected || !snapshot) {
    return {
      label: "HORS LIGNE",
      tone: "danger",
      className: "is-critical",
      description:
        "La communication avec le contrôleur est interrompue.",
    };
  }

  if (snapshot.safetySafe === false) {
    return {
      label: "SÉCURITÉ",
      tone: "danger",
      className: "is-critical",
      description:
        "Le contrôleur bloque l’exploitation pour raison de sécurité.",
    };
  }

  if (snapshot.deviceReady === false) {
    return {
      label: "NON PRÊT",
      tone: "warning",
      className: "is-warning",
      description:
        "Le matériel est connecté mais n’est pas déclaré prêt.",
    };
  }

  if (
    snapshot.pumpRunning !==
    snapshot.valveOpen
  ) {
    return {
      label: "TRANSITION",
      tone: "warning",
      className: "is-warning",
      description:
        "La séquence pompe / électrovanne est intermédiaire.",
    };
  }

  if (
    snapshot.pumpRunning &&
    snapshot.valveOpen
  ) {
    return {
      label: "EN SERVICE",
      tone: "success",
      className: "is-running",
      description:
        "Le contrôleur pilote actuellement le circuit GeoCooling.",
    };
  }

  return {
    label: "PRÊT",
    tone: "success",
    className: "is-good",
    description:
      "Le contrôleur est disponible et attend une demande de fonctionnement.",
  };
}

export function ControllerStatusCard({
  snapshot,
  connected,
}: ControllerStatusCardProps) {
  const state = controllerState(
    snapshot,
    connected,
  );

  const mode = normalizeMode(
    snapshot?.mode,
  );

  const hydraulicCoherent =
    snapshot !== null &&
    snapshot.pumpRunning ===
      snapshot.valveOpen;

  const checks: ReadinessCheck[] = [
    {
      label: "Communication backend",
      detail: connected
        ? "Connexion active"
        : "Connexion interrompue",
      valid: connected,
    },
    {
      label: "Disponibilité contrôleur",
      detail:
        snapshot?.deviceReady === true
          ? "Matériel prêt"
          : snapshot?.deviceReady === false
            ? "Matériel non prêt"
            : "État inconnu",
      valid:
        snapshot?.deviceReady === true,
      warning:
        snapshot?.deviceReady === null ||
        snapshot?.deviceReady === undefined,
    },
    {
      label: "Sécurité générale",
      detail:
        snapshot?.safetySafe === true
          ? "Conditions validées"
          : snapshot?.safetySafe === false
            ? "Blocage de sécurité"
            : "État inconnu",
      valid:
        snapshot?.safetySafe !== false &&
        snapshot?.safetySafe !== null &&
        snapshot?.safetySafe !== undefined,
      warning:
        snapshot?.safetySafe === null ||
        snapshot?.safetySafe === undefined,
    },
    {
      label: "Séquence hydraulique",
      detail: hydraulicCoherent
        ? "Pompe et vanne cohérentes"
        : "État intermédiaire détecté",
      valid: hydraulicCoherent,
      warning: !hydraulicCoherent,
    },
  ];

  const validChecks =
    checks.filter(
      (check) => check.valid,
    ).length;

  const readinessScore =
    Math.round(
      (validChecks / checks.length) * 100,
    );

  return (
    <Panel
      title="Contrôleur & readiness"
      subtitle="Disponibilité opérationnelle et sécurités"
      icon="◉"
      className="gc-controller-console"
      action={
        <StatusBadge
          label={state.label}
          tone={state.tone}
          pulse={
            state.tone === "success" &&
            state.label === "EN SERVICE"
          }
        />
      }
    >
      <section
        className={`gc-controller-summary ${state.className}`}
      >
        <div className="gc-controller-summary__indicator">
          <span />
        </div>

        <div>
          <span className="gc-controller-label">
            ÉTAT OPÉRATIONNEL
          </span>

          <strong>
            {state.description}
          </strong>
        </div>
      </section>

      <section className="gc-controller-mode">
        <header>
          <div>
            <span className="gc-controller-label">
              MODE DE PILOTAGE
            </span>

            <strong className={mode.className}>
              {mode.label}
            </strong>
          </div>

          <div
            className={`gc-controller-mode__icon ${mode.className}`}
            aria-hidden="true"
          >
            {snapshot?.mode === "automatic"
              ? "A"
              : snapshot?.mode === "manual"
                ? "M"
                : snapshot?.mode === "simulation"
                  ? "S"
                  : "?"}
          </div>
        </header>

        <p>{mode.description}</p>
      </section>

      <section className="gc-controller-readiness">
        <header>
          <div>
            <span className="gc-controller-label">
              SCORE DE READINESS
            </span>

            <strong>
              {validChecks}/{checks.length} contrôles
            </strong>
          </div>

          <div>
            <strong>
              {readinessScore}
            </strong>

            <span>%</span>
          </div>
        </header>

        <div className="gc-controller-readiness__track">
          <div
            className={
              readinessScore === 100
                ? "is-good"
                : readinessScore >= 50
                  ? "is-warning"
                  : "is-critical"
            }
            style={{
              width: `${readinessScore}%`,
            }}
          />
        </div>
      </section>

      <section className="gc-controller-equipment">
        <article
          className={
            snapshot?.valveOpen
              ? "is-active"
              : "is-idle"
          }
        >
          <div>
            <span className="gc-controller-label">
              ÉLECTROVANNE
            </span>

            <i />
          </div>

          <strong>
            {snapshot?.valveOpen
              ? "OUVERTE"
              : "FERMÉE"}
          </strong>

          <small>
            Autorisation hydraulique
          </small>
        </article>

        <article
          className={
            snapshot?.pumpRunning
              ? "is-active"
              : "is-idle"
          }
        >
          <div>
            <span className="gc-controller-label">
              CIRCULATEUR
            </span>

            <i />
          </div>

          <strong>
            {snapshot?.pumpRunning
              ? "EN MARCHE"
              : "ARRÊTÉ"}
          </strong>

          <small>
            Commande de circulation
          </small>
        </article>
      </section>

      <section className="gc-controller-checks">
        <header>
          <span className="gc-controller-label">
            CONTRÔLES DE DISPONIBILITÉ
          </span>

          <strong>
            {validChecks}/{checks.length}
          </strong>
        </header>

        <div>
          {checks.map((check) => (
            <article
              key={check.label}
              className={
                check.valid
                  ? "is-valid"
                  : check.warning
                    ? "is-warning"
                    : "is-critical"
              }
            >
              <span>
                {check.valid ? "✓" : "!"}
              </span>

              <div>
                <strong>{check.label}</strong>
                <small>{check.detail}</small>
              </div>
            </article>
          ))}
        </div>
      </section>

      <footer className="gc-controller-footer">
        <div>
          <span
            className={
              connected
                ? "is-positive"
                : "is-negative"
            }
          />

          Backend
          {connected
            ? " connecté"
            : " hors ligne"}
        </div>

        <div>
          <span
            className={
              snapshot?.deviceReady
                ? "is-positive"
                : "is-warning"
            }
          />

          Matériel
          {snapshot?.deviceReady
            ? " prêt"
            : " non prêt"}
        </div>

        <div>
          <span
            className={
              snapshot?.safetySafe === false
                ? "is-negative"
                : "is-positive"
            }
          />

          Sécurité
          {snapshot?.safetySafe === false
            ? " bloquante"
            : " validée"}
        </div>
      </footer>
    </Panel>
  );
}
