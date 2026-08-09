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

const KNOWN_NON_HYDRAULIC = new Set([
  "gc_temp_salon",
  "gc_temp_etage",
  "weather_outdoor",
]);

function displayDate(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString("fr-FR");
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
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const [discoveryResponse, sensorsResponse] = await Promise.all([
        fetch("/api/backend/geocooling/sensor-mqtt-discovery", { cache: "no-store" }),
        fetch("/api/backend/sensors/latest", { cache: "no-store" }),
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

  const upstreamEmpty = hydraulicCandidates.length === 0;
  const mqttConnected = discovery?.mqtt?.connected === true;
  const messageCount = discovery?.mqtt?.message_count ?? 0;

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
            label={upstreamEmpty ? "AMONT ABSENT" : "TÉLÉMÉTRIE OBSERVÉE"}
            tone={upstreamEmpty ? "critical" : "good"}
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
            <h2>{discovery?.discovery?.sensor_count ?? 0}</h2>
            <p>Sondes température reconnues par la découverte MQTT.</p>
          </article>

          <article className="gc-panel">
            <span className="gc-eyebrow">HYDRAULIQUE</span>
            <h2>{hydraulicCandidates.length}</h2>
            <p>Candidats surface / températures hydrauliques / débit.</p>
          </article>
        </section>

        <section className="gc-panel">
          <div className="gc-panel__header">
            <div>
              <span className="gc-eyebrow">DIAGNOSTIC</span>
              <h2>{upstreamEmpty ? "UPSTREAM_EMPTY" : "OBSERVED"}</h2>
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
              Des sources hydrauliques sont présentes. Leur identité physique doit
              être confirmée avant toute affectation à un rôle GeoCooling.
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
              <dt>Topics MQTT</dt>
              <dd>{discovery?.mqtt?.topic_count ?? 0}</dd>
            </div>
            <div>
              <dt>Heartbeat</dt>
              <dd>{discovery?.discovery?.heartbeat_topic_count ?? 0}</dd>
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
