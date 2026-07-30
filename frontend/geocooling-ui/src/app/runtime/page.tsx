"use client";

import { AppShell } from "@/components/layout/AppShell";
import {
  GeoCoolingAPI,
} from "@/lib/geocooling-api";
import {
  useGeoCoolingResource,
} from "@/hooks/useGeoCoolingResource";

type RuntimePayload = Record<string, unknown>;

type RuntimeEntry = {
  key: string;
  label: string;
  value: unknown;
};

const RUNTIME_POLLING_INTERVAL_MS = 3_000;

function loadRuntime(
  signal?: AbortSignal
): Promise<RuntimePayload> {
  return GeoCoolingAPI.runtime(
    signal
  ) as Promise<RuntimePayload>;
}

function isRecord(
  value: unknown
): value is Record<string, unknown> {
  return (
    typeof value === "object" &&
    value !== null &&
    !Array.isArray(value)
  );
}

function humanizeKey(key: string): string {
  return key
    .replace(/[_-]+/g, " ")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/\b\w/g, (letter) =>
      letter.toUpperCase()
    );
}

function flattenRuntime(
  value: unknown,
  prefix = ""
): RuntimeEntry[] {
  if (!isRecord(value)) {
    return [];
  }

  return Object.entries(value).flatMap(
    ([key, childValue]) => {
      const path = prefix
        ? `${prefix}.${key}`
        : key;

      if (isRecord(childValue)) {
        return flattenRuntime(
          childValue,
          path
        );
      }

      return [
        {
          key: path,
          label: humanizeKey(path),
          value: childValue,
        },
      ];
    }
  );
}

function formatTime(date: Date | null): string {
  if (!date) {
    return "En attente";
  }

  return date.toLocaleTimeString("fr-FR", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function formatRuntimeValue(
  value: unknown
): string {
  if (value === null || value === undefined) {
    return "Non disponible";
  }

  if (typeof value === "boolean") {
    return value ? "Actif" : "Inactif";
  }

  if (typeof value === "number") {
    return Number.isInteger(value)
      ? value.toLocaleString("fr-FR")
      : value.toLocaleString("fr-FR", {
          maximumFractionDigits: 2,
        });
  }

  if (typeof value === "string") {
    return value.length > 0
      ? value
      : "Non renseigné";
  }

  if (Array.isArray(value)) {
    if (value.length === 0) {
      return "Aucun élément";
    }

    return value
      .map((item) =>
        typeof item === "object"
          ? JSON.stringify(item)
          : String(item)
      )
      .join(", ");
  }

  return JSON.stringify(value);
}

function getValueClass(value: unknown): string {
  if (typeof value !== "boolean") {
    return "";
  }

  return value
    ? "runtime-value-positive"
    : "runtime-value-negative";
}

function getStatusLabel(
  error: string | null,
  refreshing: boolean
): string {
  if (error) {
    return "Connexion interrompue";
  }

  if (refreshing) {
    return "Actualisation…";
  }

  return "Données temps réel";
}

export default function RuntimePage() {
  const {
    data,
    loading,
    refreshing,
    error,
    lastUpdate,
    refresh,
  } = useGeoCoolingResource<RuntimePayload>(
    loadRuntime,
    {
      intervalMs:
        RUNTIME_POLLING_INTERVAL_MS,
    }
  );

  const entries = data
    ? flattenRuntime(data)
    : [];

  const connected = Boolean(
    data && !error
  );

  return (
    <AppShell connected={connected}>
      <section className="page-heading">
        <div>
          <p className="eyebrow">
            Contrôleur
          </p>

          <h1>Runtime GeoCooling</h1>

          <p className="page-copy">
            Supervision temps réel du moteur,
            de ses services et de son état
            d’exécution.
          </p>
        </div>

        <button
          className={`live-pill live-button ${
            error ? "live-error" : ""
          }`}
          type="button"
          onClick={() => void refresh()}
          disabled={refreshing}
          title="Actualiser le runtime"
        >
          <span className="live-dot" />

          {getStatusLabel(
            error,
            refreshing
          )}

          {" · "}

          {formatTime(lastUpdate)}
        </button>
      </section>

      {loading && !data ? (
        <section
          className="state-panel"
          aria-live="polite"
        >
          <div className="state-spinner" />

          <div>
            <h2>
              Lecture du runtime…
            </h2>

            <p>
              Connexion au contrôleur
              GeoCooling.
            </p>
          </div>
        </section>
      ) : null}

      {error ? (
        <section
          className="state-panel state-error"
          role="alert"
        >
          <div>
            <h2>
              Runtime indisponible
            </h2>

            <p>{error}</p>
          </div>

          <button
            type="button"
            onClick={() => void refresh()}
          >
            Réessayer
          </button>
        </section>
      ) : null}

      {data ? (
        <>
          <section className="runtime-summary">
            <article className="runtime-summary-card">
              <span className="runtime-summary-label">
                Connexion
              </span>

              <strong className="runtime-summary-value runtime-value-positive">
                Opérationnelle
              </strong>

              <small>
                API Runtime accessible
              </small>
            </article>

            <article className="runtime-summary-card">
              <span className="runtime-summary-label">
                Données exposées
              </span>

              <strong className="runtime-summary-value">
                {entries.length}
              </strong>

              <small>
                Indicateurs détectés
              </small>
            </article>

            <article className="runtime-summary-card">
              <span className="runtime-summary-label">
                Rafraîchissement
              </span>

              <strong className="runtime-summary-value">
                3 s
              </strong>

              <small>
                Polling automatique
              </small>
            </article>
          </section>

          {entries.length > 0 ? (
            <section className="runtime-grid">
              {entries.map((entry) => (
                <article
                  className="runtime-card"
                  key={entry.key}
                >
                  <span className="runtime-card-label">
                    {entry.label}
                  </span>

                  <strong
                    className={`runtime-card-value ${getValueClass(
                      entry.value
                    )}`}
                  >
                    {formatRuntimeValue(
                      entry.value
                    )}
                  </strong>

                  <code className="runtime-card-path">
                    {entry.key}
                  </code>
                </article>
              ))}
            </section>
          ) : (
            <section className="state-panel">
              <div>
                <h2>
                  Runtime accessible
                </h2>

                <p>
                  Le contrôleur n’a retourné
                  aucun indicateur exploitable.
                </p>
              </div>
            </section>
          )}

          <section className="panel runtime-raw-panel">
            <div className="panel-head">
              <div>
                <h2 className="panel-title">
                  Réponse brute
                </h2>

                <p className="panel-kicker">
                  Diagnostic technique de
                  l’endpoint runtime
                </p>
              </div>
            </div>

            <pre className="runtime-json">
              {JSON.stringify(
                data,
                null,
                2
              )}
            </pre>
          </section>
        </>
      ) : null}
    </AppShell>
  );
}
