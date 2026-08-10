"use client";

import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/layout/AppShell";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useGeoCooling } from "@/hooks/useGeoCooling";

type ReadinessState =
  | "UPSTREAM_NOT_READY"
  | "IDENTIFICATION_REQUIRED"
  | "MAPPING_INCOMPLETE"
  | "FIELD_CERTIFICATION_REQUIRED"
  | "READY_FOR_RELEASE";

type CommissioningReadiness = {
  component?: string;
  state?: ReadinessState;
  ready_for_release?: boolean;
  telemetry_ready?: boolean;
  upstream_state?: string;
  physical_identification_confirmed?: boolean;
  field_certification_confirmed?: boolean;
  configured_role_count?: number;
  role_count?: number;
  next_action?: string;
  read_only?: boolean;
  hardware_touched?: boolean;
  automatic_hardware_enable?: boolean;
  database_write?: boolean;
  mqtt_publish?: boolean;
  confirmation_sources?: {
    physical_identification?: string;
    field_certification?: string;
  };
};

type ActivationPolicy = {
  readiness_state?: string;
  controller_start_allowed?: boolean;
  manual_arm_allowed?: boolean;
  manual_positive_commands_allowed?: boolean;
  commissioning_tests_allowed?: boolean;
  safe_stop_allowed?: boolean;
  pump_stop_allowed?: boolean;
  valve_close_allowed?: boolean;
  disarm_allowed?: boolean;
  read_only?: boolean;
  hardware_touched?: boolean;
  rules?: Record<string, string>;
};

const LABELS: Record<ReadinessState, string> = {
  UPSTREAM_NOT_READY: "AMONT À RÉTABLIR",
  IDENTIFICATION_REQUIRED: "IDENTIFICATION REQUISE",
  MAPPING_INCOMPLETE: "MAPPING INCOMPLET",
  FIELD_CERTIFICATION_REQUIRED: "CERTIFICATION TERRAIN REQUISE",
  READY_FOR_RELEASE: "PRÊT POUR RELEASE",
};

const STEPS: Array<{ state: ReadinessState; label: string; description: string }> = [
  {
    state: "UPSTREAM_NOT_READY",
    label: "1. Télémétrie amont",
    description: "WT32 / ESPHome publie réellement les sondes vers MQTT.",
  },
  {
    state: "IDENTIFICATION_REQUIRED",
    label: "2. Identification physique",
    description: "Chaque DS18B20 est associé manuellement à son rôle réel.",
  },
  {
    state: "MAPPING_INCOMPLETE",
    label: "3. Mapping et fraîcheur",
    description: "Les six rôles sont configurés et leurs mesures sont toutes OK.",
  },
  {
    state: "FIELD_CERTIFICATION_REQUIRED",
    label: "4. Certification terrain",
    description: "EV puis M11/M13 sont testés physiquement avec les sécurités actives.",
  },
  {
    state: "READY_FOR_RELEASE",
    label: "5. Release",
    description: "Tous les gates sont satisfaits et la release peut être préparée.",
  },
];

function stateIndex(state?: ReadinessState): number {
  if (!state) return -1;
  return STEPS.findIndex((step) => step.state === state);
}

function permissionLabel(value?: boolean): string {
  return value === true ? "AUTORISÉ" : "BLOQUÉ";
}

export default function CommissioningPage() {
  const {
    connected,
    refreshing,
    lastUpdate,
    responseTime,
    snapshot,
    refresh,
  } = useGeoCooling();

  const [readiness, setReadiness] = useState<CommissioningReadiness | null>(null);
  const [policy, setPolicy] = useState<ActivationPolicy | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [readinessResponse, policyResponse] = await Promise.all([
        fetch(
          "/api/geocooling/brain-v2/integration/home-assistant/commissioning-readiness",
          { cache: "no-store" },
        ),
        fetch(
          "/api/geocooling/brain-v2/integration/home-assistant/hardware-activation-policy",
          { cache: "no-store" },
        ),
      ]);
      if (!readinessResponse.ok) {
        throw new Error(`Commissioning HTTP ${readinessResponse.status}`);
      }
      if (!policyResponse.ok) {
        throw new Error(`Activation policy HTTP ${policyResponse.status}`);
      }
      setReadiness((await readinessResponse.json()) as CommissioningReadiness);
      setPolicy((await policyResponse.json()) as ActivationPolicy);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Erreur commissioning");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), 10_000);
    return () => window.clearInterval(timer);
  }, [load]);

  const currentIndex = stateIndex(readiness?.state);
  const refreshAll = useCallback(() => {
    refresh();
    void load();
  }, [load, refresh]);

  const commandPaths = [
    {
      label: "START normal",
      allowed: policy?.controller_start_allowed,
      rule: policy?.rules?.controller_start,
    },
    {
      label: "Armement manuel",
      allowed: policy?.manual_arm_allowed,
      rule: policy?.rules?.manual_arm,
    },
    {
      label: "Commandes manuelles ON",
      allowed: policy?.manual_positive_commands_allowed,
      rule: policy?.rules?.manual_positive_commands,
    },
    {
      label: "Tests physiques commissioning",
      allowed: policy?.commissioning_tests_allowed,
      rule: policy?.rules?.commissioning_tests,
    },
  ];

  return (
    <AppShell
      connected={connected}
      mode={snapshot?.mode}
      refreshing={refreshing || loading}
      lastUpdate={lastUpdate}
      generatedAt={snapshot?.generatedAt}
      responseTime={responseTime}
      onRefresh={refreshAll}
    >
      <div className="gc-page">
        <header className="gc-page-header">
          <div>
            <span className="gc-eyebrow">MISE EN SERVICE</span>
            <h1>Commissioning</h1>
            <p>Progression fail-safe depuis la télémétrie jusqu’à la release.</p>
          </div>
          <StatusBadge
            label={readiness?.state ? LABELS[readiness.state] : "INCONNU"}
            tone={readiness?.ready_for_release ? "success" : "warning"}
          />
        </header>

        {error ? (
          <section className="gc-panel">
            <h2>Erreur de lecture</h2>
            <p>{error}</p>
          </section>
        ) : null}

        <section className="gc-grid gc-grid--3">
          <article className="gc-panel">
            <span className="gc-eyebrow">RÔLES TÉLÉMÉTRIQUES</span>
            <h2>{readiness?.configured_role_count ?? 0} / {readiness?.role_count ?? 6}</h2>
            <p>{readiness?.telemetry_ready ? "Six rôles frais et valides." : "Télémétrie encore incomplète."}</p>
          </article>
          <article className="gc-panel">
            <span className="gc-eyebrow">IDENTIFICATION</span>
            <h2>{readiness?.physical_identification_confirmed ? "Confirmée" : "Non confirmée"}</h2>
            <p>Confirmation humaine obligatoire, jamais auto-déduite.</p>
          </article>
          <article className="gc-panel">
            <span className="gc-eyebrow">TERRAIN</span>
            <h2>{readiness?.field_certification_confirmed ? "Certifié" : "À certifier"}</h2>
            <p>EV et M11/M13 restent un gate physique distinct.</p>
          </article>
        </section>

        <section className="gc-panel">
          <div className="gc-panel__header">
            <div>
              <span className="gc-eyebrow">PROCHAINE ACTION</span>
              <h2>{readiness?.state ? LABELS[readiness.state] : "État indisponible"}</h2>
            </div>
          </div>
          <p>{readiness?.next_action ?? "Lecture du gate en cours."}</p>
        </section>

        <section className="gc-panel">
          <div className="gc-panel__header">
            <div>
              <span className="gc-eyebrow">POLITIQUE D’ACTIVATION</span>
              <h2>Chemins de commande</h2>
            </div>
            <StatusBadge label="READ-ONLY" tone="success" />
          </div>
          <p>
            Cette matrice est calculée côté backend. Elle n’exécute aucune commande et
            permet de vérifier qu’un chemin alternatif ne contourne pas les gates.
          </p>
          <div className="gc-table-wrap">
            <table className="gc-table">
              <thead>
                <tr>
                  <th>Chemin</th>
                  <th>État</th>
                  <th>Règle</th>
                </tr>
              </thead>
              <tbody>
                {commandPaths.map((path) => (
                  <tr key={path.label}>
                    <td>{path.label}</td>
                    <td>
                      <StatusBadge
                        label={permissionLabel(path.allowed)}
                        tone={path.allowed === true ? "success" : "warning"}
                      />
                    </td>
                    <td>{path.rule ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p>
            Les actions de repli restent toujours autorisées : arrêt pompe, fermeture EV,
            safe-stop et désarmement.
          </p>
        </section>

        <section className="gc-panel">
          <div className="gc-panel__header">
            <div>
              <span className="gc-eyebrow">GATES DE MISE EN SERVICE</span>
              <h2>Progression</h2>
            </div>
          </div>
          <div className="gc-table-wrap">
            <table className="gc-table">
              <thead>
                <tr>
                  <th>Étape</th>
                  <th>État</th>
                  <th>Critère</th>
                </tr>
              </thead>
              <tbody>
                {STEPS.map((step, index) => {
                  const complete = currentIndex > index || readiness?.ready_for_release === true;
                  const current = currentIndex === index;
                  return (
                    <tr key={step.state}>
                      <td>{step.label}</td>
                      <td>
                        <StatusBadge
                          label={complete ? "VALIDÉ" : current ? "EN COURS" : "À VENIR"}
                          tone={complete ? "success" : current ? "warning" : "neutral"}
                        />
                      </td>
                      <td>{step.description}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>

        <section className="gc-panel">
          <div className="gc-panel__header">
            <div>
              <span className="gc-eyebrow">GARDE-FOUS</span>
              <h2>Lecture seule</h2>
            </div>
            <StatusBadge label="AUCUN ACTIONNEMENT" tone="success" />
          </div>
          <dl className="gc-definition-list">
            <div><dt>Hardware touché</dt><dd>{readiness?.hardware_touched === false && policy?.hardware_touched === false ? "Non" : "Inconnu"}</dd></div>
            <div><dt>Activation automatique</dt><dd>{readiness?.automatic_hardware_enable === false ? "Interdite" : "Inconnue"}</dd></div>
            <div><dt>Écriture DB</dt><dd>{readiness?.database_write === false ? "Aucune" : "Inconnue"}</dd></div>
            <div><dt>Publication MQTT</dt><dd>{readiness?.mqtt_publish === false ? "Aucune" : "Inconnue"}</dd></div>
          </dl>
          <p>
            Les confirmations restent locales dans <code>{readiness?.confirmation_sources?.physical_identification ?? "GEOCOOLING_SENSOR_IDENTIFICATION_CONFIRMED"}</code> et <code>{readiness?.confirmation_sources?.field_certification ?? "GEOCOOLING_FIELD_CERTIFICATION_CONFIRMED"}</code>. Elles n’arment aucun relais.
          </p>
        </section>
      </div>
    </AppShell>
  );
}
