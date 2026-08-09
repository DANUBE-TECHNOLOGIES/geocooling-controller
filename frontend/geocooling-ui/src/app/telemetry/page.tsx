"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/layout/AppShell";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useGeoCooling } from "@/hooks/useGeoCooling";

type DiscoveryStatus = {
  running?: boolean;
  passive_only?: boolean;
  mqtt?: {
    connected?: boolean;
    connection_error?: string | null;
    last_message_at?: string | null;
    message_count?: number;
    topic_count?: number;
  };
  discovery?: {
    sensor_count?: number;
    heartbeat_topic_count?: number;
    relay_topic_count?: number;
  };
};

type LatestSensor = {
  sensor_name?: string;
  metric?: string;
  value?: number | string | null;
  unit?: string | null;
  measured_at?: string | null;
  mqtt_topic?: string | null;
};

type HomeAssistantState = {
  version?: string;
  available?: boolean;
  advisory_only?: boolean;
  decision_authority?: boolean;
  hardware_control?: boolean;
  fail_safe_missing_values?: boolean;
  telemetry_complete?: boolean;
  hydraulic_role_count?: number;
  hydraulic_roles_ready?: number;
  missing_measurements?: string[];
};

type TelemetryRoleState = "UNSET" | "SOURCE_ABSENT" | "METRIC_ABSENT" | "STALE" | "OK";

type TelemetryRoleHealth = {
  role?: string;
  env_var?: string | null;
  sensor_name?: string | null;
  metric?: string;
  state?: TelemetryRoleState;
  ready?: boolean;
  reason?: string;
  stale_seconds?: number;
  measured_at?: string | null;
  age_seconds?: number | null;
  value?: number | string | null;
  unit?: string | null;
  mqtt_topic?: string | null;
};

type TelemetryCandidate = {
  sensor_name?: string;
  metrics?: string[];
  mqtt_topics?: string[];
};

type TelemetryHealth = {
  component?: string;
  ready?: boolean;
  fail_closed?: boolean;
  stale_seconds?: number;
  upstream_state?: "UPSTREAM_EMPTY" | "OBSERVED" | string;
  observed_sensor_count?: number;
  hydraulic_candidate_count?: number;
  configured_role_count?: number;
  auto_assignment_allowed?: boolean;
  physical_confirmation_required?: boolean;
  candidate_sensors?: TelemetryCandidate[];
  roles?: Record<string, TelemetryRoleHealth>;
  read_only?: boolean;
  hardware_touched?: boolean;
  mqtt_publish?: boolean;
  database_write?: boolean;
};

const KNOWN_NON_HYDRAULIC = new Set([
  "gc_temp_salon",
  "gc_temp_etage",
  "weather_outdoor",
]);

const ROLE_LABELS: Record<string, string> = {
  surface: "Surface plancher",
  floor_supply: "Départ plancher",
  floor_return: "Retour plancher",
  source_inlet: "Entrée source",
  source_outlet: "Sortie source",
  flow: "Débit hydraulique",
  floor_surface_temperature_c: "Surface plancher",
  floor_supply_temperature_c: "Départ plancher",
  floor_return_temperature_c: "Retour plancher",
  source_inlet_temperature_c: "Entrée source",
  source_outlet_temperature_c: "Sortie source",
  flow_rate_l_min: "Débit hydraulique",
};

const STATE_LABELS: Record<TelemetryRoleState, string> = {
  UNSET: "NON CONFIGURÉ",
  SOURCE_ABSENT: "SOURCE ABSENTE",
  METRIC_ABSENT: "MÉTRIQUE ABSENTE",
  STALE: "PÉRIMÉE",
  OK: "OK",
};

function displayDate(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString("fr-FR");
}

function displayRoleValue(role: TelemetryRoleHealth): string {
  if (role.value === null || role.value === undefined) return "—";
  return `${role.value}${role.unit ? ` ${role.unit}` : ""}`;
}

export default function TelemetryPage() {
  const {
    connected,
    refreshing,
    lastUpdate,
    responseTime,
    snapshot,
    refresh,
  } = useGeoCooling();

  const [discovery, setDiscovery] = useState<DiscoveryStatus | null>(null);
  const [rows, setRows] = useState<LatestSensor[]>([]);
  const [homeAssistant, setHomeAssistant] = useState<HomeAssistantState | null>(null);
  const [telemetryHealth, setTelemetryHealth] = useState<TelemetryHealth | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const [
        discoveryResponse,
        sensorsResponse,
        homeAssistantResponse,
        telemetryHealthResponse,
      ] = await Promise.all([
        fetch("/api/geocooling/sensor-mqtt-discovery", { cache: "no-store" }),
        fetch("/api/sensors/latest", { cache: "no-store" }),
        fetch("/api/geocooling/brain-v2/integration/home-assistant/state", {
          cache: "no-store",
        }),
        fetch("/api/geocooling/brain-v2/integration/home-assistant/telemetry-health", {
          cache: "no-store",
        }),
      ]);

      if (!discoveryResponse.ok) {
        throw new Error(`Discovery HTTP ${discoveryResponse.status}`);
      }
      if (!sensorsResponse.ok) {
        throw new Error(`Sensors HTTP ${sensorsResponse.status}`);
      }

      setDiscovery((await discoveryResponse.json()) as DiscoveryStatus);
      const payload = await sensorsResponse.json();
      setRows(Array.isArray(payload) ? (payload as LatestSensor[]) : []);

      if (homeAssistantResponse.ok) {
        setHomeAssistant((await homeAssistantResponse.json()) as HomeAssistantState);
      } else {
        setHomeAssistant(null);
      }

      if (telemetryHealthResponse.ok) {
        setTelemetryHealth((await telemetryHealthResponse.json()) as TelemetryHealth);
      } else {
        setTelemetryHealth(null);
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Erreur télémétrie");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), 10_000);
    return () => window.clearInterval(timer);
  }, [load]);

  const hydraulicCandidates = useMemo(() => {
    const names = new Set<string>();
    for (const row of rows) {
      const name = (row.sensor_name ?? "").trim();
      const metric = (row.metric ?? "").trim();
      if (
        name &&
        !KNOWN_NON_HYDRAULIC.has(name) &&
        (metric === "temperature" || metric === "flow")
      ) {
        names.add(name);
      }
    }
    return [...names].sort();
  }, [rows]);

  const roleHealth = useMemo(
    () => Object.entries(telemetryHealth?.roles ?? {}),
    [telemetryHealth]
  );

  const candidates = telemetryHealth?.candidate_sensors ?? [];
  const upstreamEmpty = telemetryHealth
    ? telemetryHealth.upstream_state === "UPSTREAM_EMPTY"
    : hydraulicCandidates.length === 0;
  const mqttConnected = discovery?.mqtt?.connected === true;
  const messageCount = discovery?.mqtt?.message_count ?? 0;
  const missingRoles = homeAssistant?.missing_measurements ?? [];
  const readyRoles = telemetryHealth
    ? roleHealth.filter(([, role]) => role.ready === true).length
    : homeAssistant?.hydraulic_roles_ready ?? 0;
  const roleCount = roleHealth.length || homeAssistant?.hydraulic_role_count || 6;

  const refreshAll = useCallback(() => {
    refresh();
    void load();
  }, [load, refresh]);

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
            <span className="gc-eyebrow">TECHNIQUE</span>
            <h1>Télémétrie</h1>
            <p>Chaîne passive WT32 / ESPHome → MQTT → GeoCooling.</p>
          </div>
          <StatusBadge
            label={
              telemetryHealth?.ready
                ? "6 RÔLES PRÊTS"
                : upstreamEmpty
                  ? "AMONT ABSENT"
                  : "FAIL-CLOSED"
            }
            tone={telemetryHealth?.ready ? "success" : "danger"}
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
            <span className="gc-eyebrow">MQTT</span>
            <h2>{mqttConnected ? "Connecté" : "Non connecté"}</h2>
            <p>{messageCount} messages observés par le discovery backend.</p>
          </article>

          <article className="gc-panel">
            <span className="gc-eyebrow">SONDES</span>
            <h2>{telemetryHealth?.observed_sensor_count ?? discovery?.discovery?.sensor_count ?? 0}</h2>
            <p>Sources actuellement observées par la chaîne de télémétrie.</p>
          </article>

          <article className="gc-panel">
            <span className="gc-eyebrow">RÔLES HYDRAULIQUES</span>
            <h2>{readyRoles} / {roleCount}</h2>
            <p>{telemetryHealth?.configured_role_count ?? 0} rôles configurés, seuil de fraîcheur {telemetryHealth?.stale_seconds ?? 120} s.</p>
          </article>
        </section>

        <section className="gc-panel">
          <div className="gc-panel__header">
            <div>
              <span className="gc-eyebrow">SOURCE DE VÉRITÉ BACKEND</span>
              <h2>{telemetryHealth?.ready ? "Télémétrie hydraulique prête" : "Télémétrie hydraulique incomplète"}</h2>
            </div>
            <StatusBadge
              label={telemetryHealth?.fail_closed === false ? "READY" : "FAIL-CLOSED"}
              tone={telemetryHealth?.fail_closed === false ? "success" : "warning"}
            />
          </div>

          <p>
            Chaque rôle est évalué côté backend à partir du mapping configuré, de la
            présence réelle de la source, de la métrique attendue et de la fraîcheur
            de la dernière mesure. L’interface ne recalcule plus ce diagnostic.
          </p>

          <div className="gc-table-wrap">
            <table className="gc-table">
              <thead>
                <tr>
                  <th>Rôle</th>
                  <th>État</th>
                  <th>Variable .env</th>
                  <th>Capteur configuré</th>
                  <th>Valeur</th>
                  <th>Âge</th>
                  <th>Dernière mesure</th>
                </tr>
              </thead>
              <tbody>
                {roleHealth.map(([roleName, role]) => {
                  const state = role.state ?? "UNSET";
                  return (
                    <tr key={roleName}>
                      <td>{ROLE_LABELS[roleName] ?? roleName}</td>
                      <td>
                        <StatusBadge
                          label={STATE_LABELS[state]}
                          tone={state === "OK" ? "success" : state === "STALE" ? "warning" : "danger"}
                        />
                      </td>
                      <td><code>{role.env_var ?? "—"}</code></td>
                      <td>{role.sensor_name ?? "—"}</td>
                      <td>{displayRoleValue(role)}</td>
                      <td>{role.age_seconds === null || role.age_seconds === undefined ? "—" : `${Math.round(role.age_seconds)} s`}</td>
                      <td>{displayDate(role.measured_at)}</td>
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
              <span className="gc-eyebrow">IDENTIFICATION PHYSIQUE</span>
              <h2>{candidates.length} candidat{candidates.length === 1 ? "" : "s"} observé{candidates.length === 1 ? "" : "s"}</h2>
            </div>
            <StatusBadge
              label={telemetryHealth?.physical_confirmation_required === true ? "CONFIRMATION OBLIGATOIRE" : "NON CERTIFIÉ"}
              tone="warning"
            />
          </div>

          <p>
            GeoCooling n’affecte jamais automatiquement un capteur à un rôle physique.
            Une température plausible ne suffit pas à distinguer départ, retour,
            source ou surface. Chaque identité doit être confirmée sur l’installation.
          </p>

          <dl className="gc-definition-list">
            <div>
              <dt>Auto-affectation</dt>
              <dd>{telemetryHealth?.auto_assignment_allowed === false ? "Interdite" : "Inconnue"}</dd>
            </div>
            <div>
              <dt>Confirmation physique</dt>
              <dd>{telemetryHealth?.physical_confirmation_required === true ? "Obligatoire" : "Inconnue"}</dd>
            </div>
          </dl>

          {candidates.length > 0 ? (
            <div className="gc-table-wrap">
              <table className="gc-table">
                <thead>
                  <tr>
                    <th>Capteur candidat</th>
                    <th>Métriques</th>
                    <th>Topics MQTT</th>
                  </tr>
                </thead>
                <tbody>
                  {candidates.map((candidate) => (
                    <tr key={candidate.sensor_name ?? JSON.stringify(candidate)}>
                      <td>{candidate.sensor_name ?? "—"}</td>
                      <td>{candidate.metrics?.join(", ") || "—"}</td>
                      <td>{candidate.mqtt_topics?.join(", ") || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p>Aucun candidat hydraulique n’est encore visible sur MQTT.</p>
          )}
        </section>

        <section className="gc-panel">
          <div className="gc-panel__header">
            <div>
              <span className="gc-eyebrow">HOME ASSISTANT</span>
              <h2>{homeAssistant ? `${readyRoles} / ${roleCount} rôles prêts` : "Bridge indisponible"}</h2>
            </div>
            <StatusBadge
              label={homeAssistant?.telemetry_complete ? "BRIDGE COMPLET" : "FAIL-SAFE"}
              tone={homeAssistant?.telemetry_complete ? "success" : "warning"}
            />
          </div>

          <p>
            Le bridge reste en conseil uniquement et ne possède aucune autorité
            de commande. Les mesures absentes restent inconnues : elles ne sont
            jamais converties artificiellement à zéro.
          </p>

          <dl className="gc-definition-list">
            <div>
              <dt>Valeurs manquantes fail-safe</dt>
              <dd>{homeAssistant?.fail_safe_missing_values === true ? "Actif" : "Inconnu"}</dd>
            </div>
            <div>
              <dt>Autorité décisionnelle</dt>
              <dd>{homeAssistant?.decision_authority === false ? "Aucune" : "Inconnue"}</dd>
            </div>
            <div>
              <dt>Contrôle hardware</dt>
              <dd>{homeAssistant?.hardware_control === false ? "Désactivé" : "Inconnu"}</dd>
            </div>
            <div>
              <dt>Lecture backend</dt>
              <dd>{telemetryHealth?.read_only === true && telemetryHealth?.database_write === false ? "Read-only" : "Inconnue"}</dd>
            </div>
          </dl>

          {missingRoles.length > 0 ? (
            <p>
              Mesures absentes du snapshot Brain : {missingRoles.map((role) => ROLE_LABELS[role] ?? role).join(", ")}.
            </p>
          ) : null}
        </section>

        <section className="gc-panel">
          <div className="gc-panel__header">
            <div>
              <span className="gc-eyebrow">DIAGNOSTIC AMONT</span>
              <h2>{telemetryHealth?.upstream_state ?? (upstreamEmpty ? "UPSTREAM_EMPTY" : "OBSERVED")}</h2>
            </div>
          </div>

          {upstreamEmpty ? (
            <p>
              Aucune télémétrie hydraulique, surface ou débit n’est observée.
              Modifier les mappings .env ne peut pas corriger cet état : il faut
              d’abord restaurer la publication WT32 / ESPHome vers MQTT.
            </p>
          ) : (
            <p>
              Des sources hydrauliques sont présentes. Le tableau des rôles indique
              désormais précisément si le blocage vient du mapping, de la source,
              de la métrique ou de la fraîcheur de la donnée.
            </p>
          )}

          <dl className="gc-definition-list">
            <div>
              <dt>Discovery passif</dt>
              <dd>{discovery?.passive_only === true ? "Oui" : "Inconnu"}</dd>
            </div>
            <div>
              <dt>Dernier message MQTT</dt>
              <dd>{displayDate(discovery?.mqtt?.last_message_at)}</dd>
            </div>
            <div>
              <dt>Candidats hydrauliques</dt>
              <dd>{telemetryHealth?.hydraulic_candidate_count ?? hydraulicCandidates.length}</dd>
            </div>
            <div>
              <dt>Commande hardware</dt>
              <dd>{telemetryHealth?.hardware_touched === false ? "Aucune" : "Inconnue"}</dd>
            </div>
          </dl>
        </section>

        <section className="gc-panel">
          <div className="gc-panel__header">
            <div>
              <span className="gc-eyebrow">SOURCES OBSERVÉES</span>
              <h2>{rows.length} mesures récentes</h2>
            </div>
          </div>

          <div className="gc-table-wrap">
            <table className="gc-table">
              <thead>
                <tr>
                  <th>Capteur</th>
                  <th>Métrique</th>
                  <th>Valeur</th>
                  <th>Dernière mesure</th>
                  <th>Topic</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, index) => (
                  <tr key={`${row.sensor_name}-${row.metric}-${index}`}>
                    <td>{row.sensor_name ?? "—"}</td>
                    <td>{row.metric ?? "—"}</td>
                    <td>{row.value ?? "—"} {row.unit ?? ""}</td>
                    <td>{displayDate(row.measured_at)}</td>
                    <td>{row.mqtt_topic ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </AppShell>
  );
}
