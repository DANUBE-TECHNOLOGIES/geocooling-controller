"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { GeoCoolingAPI } from "@/lib/geocooling-api";
import { useGeoCoolingResource } from "@/hooks/useGeoCoolingResource";

type RuntimePayload = Record<string, unknown>;

type RuntimeEntry = {
  key: string;
  label: string;
  value: unknown;
  group: string;
};

type RuntimeState = {
  label: string;
  tone: "success" | "warning" | "danger" | "neutral";
  description: string;
};

const RUNTIME_POLLING_INTERVAL_MS = 3_000;

function loadRuntime(
  signal?: AbortSignal,
): Promise<RuntimePayload> {
  return GeoCoolingAPI.runtime(
    signal,
  ) as Promise<RuntimePayload>;
}

function isRecord(
  value: unknown,
): value is Record<string, unknown> {
  return (
    typeof value === "object" &&
    value !== null &&
    !Array.isArray(value)
  );
}

function humanizeKey(key: string): string {
  return key
    .split(".")
    .at(-1)!
    .replace(/[_-]+/g, " ")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/\b\w/g, (letter) =>
      letter.toUpperCase(),
    );
}

function flattenRuntime(
  value: unknown,
  prefix = "",
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
          path,
        );
      }

      return [
        {
          key: path,
          label: humanizeKey(path),
          value: childValue,
          group:
            path.includes(".")
              ? path.split(".")[0]
              : "runtime",
        },
      ];
    },
  );
}

function formatRuntimeValue(
  value: unknown,
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
          maximumFractionDigits: 3,
        });
  }

  if (typeof value === "string") {
    if (value.length === 0) {
      return "Non renseigné";
    }

    const date = new Date(value);

    if (
      !Number.isNaN(date.getTime()) &&
      /date|time|timestamp|generated|updated/i.test(
        value,
      )
    ) {
      return date.toLocaleString("fr-FR");
    }

    return value;
  }

  if (Array.isArray(value)) {
    return value.length === 0
      ? "Aucun élément"
      : value
          .map((item) =>
            typeof item === "object"
              ? JSON.stringify(item)
              : String(item),
          )
          .join(", ");
  }

  return JSON.stringify(value);
}

function runtimeState(
  connected: boolean,
  error: string | null,
  responseTime: number,
): RuntimeState {
  if (!connected || error) {
    return {
      label: "INDISPONIBLE",
      tone: "danger",
      description:
        "L’endpoint runtime ne fournit plus de données.",
    };
  }

  if (responseTime >= 1500) {
    return {
      label: "DÉGRADÉ",
      tone: "warning",
      description:
        "Le runtime répond avec une latence élevée.",
    };
  }

  return {
    label: "OPÉRATIONNEL",
    tone: "success",
    description:
      "Le runtime et ses services répondent normalement.",
  };
}

function valueTone(
  value: unknown,
): string {
  if (typeof value !== "boolean") {
    return "is-neutral";
  }

  return value
    ? "is-positive"
    : "is-negative";
}

function modeFromPayload(
  data: RuntimePayload | null,
): string {
  if (!data) {
    return "INCONNU";
  }

  const candidates = [
    data.mode,
    data.runtime_mode,
    data.controller_mode,
  ];

  const mode = candidates.find(
    (value) => typeof value === "string",
  );

  return typeof mode === "string"
    ? mode
    : "INCONNU";
}

export default function RuntimePage() {
  const {
    data,
    loading,
    refreshing,
    error,
    lastUpdate,
    responseTime,
    refresh,
  } = useGeoCoolingResource<RuntimePayload>(
    loadRuntime,
    {
      intervalMs:
        RUNTIME_POLLING_INTERVAL_MS,
    },
  );

  const [search, setSearch] =
    useState("");

  const [showRaw, setShowRaw] =
    useState(false);

  const entries = useMemo(
    () =>
      data
        ? flattenRuntime(data)
        : [],
    [data],
  );

  const filteredEntries = useMemo(() => {
    const normalized =
      search.trim().toLowerCase();

    if (!normalized) {
      return entries;
    }

    return entries.filter(
      (entry) =>
        entry.label
          .toLowerCase()
          .includes(normalized) ||
        entry.key
          .toLowerCase()
          .includes(normalized) ||
        formatRuntimeValue(entry.value)
          .toLowerCase()
          .includes(normalized),
    );
  }, [entries, search]);

  const groups = useMemo(
    () =>
      Array.from(
        new Set(
          entries.map(
            (entry) => entry.group,
          ),
        ),
      ),
    [entries],
  );

  const booleanEntries =
    entries.filter(
      (entry) =>
        typeof entry.value === "boolean",
    );

  const activeBooleanCount =
    booleanEntries.filter(
      (entry) => entry.value === true,
    ).length;

  const connected = Boolean(
    data && !error,
  );

  const state = runtimeState(
    connected,
    error,
    responseTime,
  );

  return (
    <AppShell
      connected={connected}
      mode={modeFromPayload(data)}
      refreshing={refreshing}
      lastUpdate={lastUpdate}
      responseTime={responseTime}
      onRefresh={() => {
        void refresh();
      }}
    >
      <section className="gc-page-header">
        <div>
          <p className="gc-page-header__eyebrow">
            OBSERVABILITÉ TECHNIQUE
          </p>

          <h2>Runtime GeoCooling</h2>

          <p>
            Inspection temps réel du moteur,
            de ses services, de sa configuration
            et des indicateurs exposés par
            l’endpoint runtime.
          </p>
        </div>

        <div className="gc-page-header__actions">
          <Link
            href="/"
            className="gc-page-link"
          >
            ← Dashboard
          </Link>

          <StatusBadge
            label={state.label}
            tone={state.tone}
            pulse={
              state.tone === "success"
            }
          />
        </div>
      </section>

      {loading && !data ? (
        <section className="gc-loading-state">
          <div className="gc-loading-spinner" />

          <div>
            <strong>
              Lecture du runtime…
            </strong>

            <span>
              Connexion à l’endpoint
              de diagnostic.
            </span>
          </div>
        </section>
      ) : null}

      {error ? (
        <section
          className="gc-error-banner"
          role="alert"
        >
          <div>
            <strong>
              Runtime indisponible
            </strong>

            <p>{error}</p>
          </div>

          <button
            type="button"
            onClick={() => {
              void refresh();
            }}
          >
            Réessayer
          </button>
        </section>
      ) : null}

      <section className="gc-runtime-page-overview">
        <article
          className={`gc-runtime-page-state ${
            state.tone === "success"
              ? "is-good"
              : state.tone === "warning"
                ? "is-warning"
                : "is-critical"
          }`}
        >
          <div>
            <span />
          </div>

          <section>
            <span className="gc-runtime-page-label">
              ÉTAT GLOBAL
            </span>

            <strong>
              {state.description}
            </strong>
          </section>
        </article>

        <article>
          <span className="gc-runtime-page-label">
            LATENCE ENDPOINT
          </span>

          <strong>
            {responseTime > 0
              ? `${responseTime} ms`
              : "—"}
          </strong>

          <small>
            Polling toutes les 3 secondes
          </small>
        </article>

        <article>
          <span className="gc-runtime-page-label">
            INDICATEURS
          </span>

          <strong>
            {entries.length}
          </strong>

          <small>
            Valeurs aplaties
          </small>
        </article>

        <article>
          <span className="gc-runtime-page-label">
            GROUPES
          </span>

          <strong>
            {groups.length}
          </strong>

          <small>
            Sections détectées
          </small>
        </article>

        <article>
          <span className="gc-runtime-page-label">
            ÉTATS ACTIFS
          </span>

          <strong>
            {activeBooleanCount}/
            {booleanEntries.length}
          </strong>

          <small>
            Valeurs booléennes
          </small>
        </article>
      </section>

      <section className="gc-runtime-page-toolbar">
        <label>
          <span>
            Rechercher un indicateur
          </span>

          <input
            type="search"
            value={search}
            onChange={(event) =>
              setSearch(event.target.value)
            }
            placeholder="Ex. driver, mqtt, ready, mode…"
          />
        </label>

        <div>
          <span>
            {filteredEntries.length}
            {" "}
            résultat(s)
          </span>

          <button
            type="button"
            onClick={() =>
              setShowRaw((current) => !current)
            }
          >
            {showRaw
              ? "Masquer JSON"
              : "Afficher JSON"}
          </button>
        </div>
      </section>

      {filteredEntries.length > 0 ? (
        <section className="gc-runtime-page-groups">
          {groups.map((group) => {
            const groupEntries =
              filteredEntries.filter(
                (entry) =>
                  entry.group === group,
              );

            if (
              groupEntries.length === 0
            ) {
              return null;
            }

            return (
              <article
                key={group}
                className="gc-runtime-page-group"
              >
                <header>
                  <div>
                    <span className="gc-runtime-page-label">
                      GROUPE
                    </span>

                    <h3>
                      {humanizeKey(group)}
                    </h3>
                  </div>

                  <strong>
                    {groupEntries.length}
                  </strong>
                </header>

                <div>
                  {groupEntries.map(
                    (entry) => (
                      <article
                        key={entry.key}
                        className="gc-runtime-page-entry"
                      >
                        <header>
                          <span>
                            {entry.label}
                          </span>

                          {typeof entry.value ===
                          "boolean" ? (
                            <i
                              className={
                                entry.value
                                  ? "is-positive"
                                  : "is-negative"
                              }
                            />
                          ) : null}
                        </header>

                        <strong
                          className={valueTone(
                            entry.value,
                          )}
                        >
                          {formatRuntimeValue(
                            entry.value,
                          )}
                        </strong>

                        <code>
                          {entry.key}
                        </code>
                      </article>
                    ),
                  )}
                </div>
              </article>
            );
          })}
        </section>
      ) : (
        <section className="gc-runtime-page-empty">
          <strong>
            Aucun indicateur trouvé
          </strong>

          <p>
            Modifie la recherche ou vérifie
            la réponse de l’endpoint runtime.
          </p>
        </section>
      )}

      {showRaw && data ? (
        <section className="gc-runtime-page-raw">
          <header>
            <div>
              <span className="gc-runtime-page-label">
                DIAGNOSTIC BRUT
              </span>

              <h3>
                Réponse JSON
              </h3>
            </div>

            <strong>
              Lecture seule
            </strong>
          </header>

          <pre>
            {JSON.stringify(
              data,
              null,
              2,
            )}
          </pre>
        </section>
      ) : null}
    </AppShell>
  );
}
