"use client";

import { useEffect } from "react";

type ErrorPageProps = {
  error: Error & {
    digest?: string;
  };
  reset: () => void;
};

export default function ErrorPage({
  error,
  reset,
}: ErrorPageProps) {
  useEffect(() => {
    console.error(
      "[GeoCooling UI] Route failure",
      error,
    );
  }, [error]);

  return (
    <main className="gc-route-state">
      <section
        className="gc-route-state__card is-error"
        role="alert"
      >
        <div
          className="gc-route-state__icon"
          aria-hidden="true"
        >
          !
        </div>

        <p className="gc-route-state__eyebrow">
          ERREUR DE PAGE
        </p>

        <h1>
          Cette console n’a pas pu être affichée
        </h1>

        <p>
          Les autres modules de supervision restent
          disponibles. La panne concerne uniquement le rendu
          de cette route.
        </p>

        <dl>
          <div>
            <dt>Message</dt>
            <dd>
              {error.message || "Erreur inconnue"}
            </dd>
          </div>

          <div>
            <dt>Digest</dt>
            <dd>
              {error.digest || "Non disponible"}
            </dd>
          </div>
        </dl>

        <div className="gc-route-state__actions">
          <button
            type="button"
            onClick={reset}
          >
            Réessayer
          </button>

          <a href="/">
            Retour au dashboard
          </a>
        </div>
      </section>
    </main>
  );
}
