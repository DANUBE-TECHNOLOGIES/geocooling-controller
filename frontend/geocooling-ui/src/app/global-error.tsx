"use client";

type GlobalErrorProps = {
  error: Error & {
    digest?: string;
  };
  reset: () => void;
};

export default function GlobalError({
  error,
  reset,
}: GlobalErrorProps) {
  return (
    <html lang="fr">
      <body>
        <main className="gc-fatal-shell">
          <section
            className="gc-fatal-card"
            role="alert"
          >
            <div
              className="gc-fatal-card__icon"
              aria-hidden="true"
            >
              !
            </div>

            <p className="gc-fatal-card__eyebrow">
              ERREUR GLOBALE
            </p>

            <h1>
              GeoCooling Enterprise ne peut pas démarrer
            </h1>

            <p className="gc-fatal-card__description">
              Une erreur critique empêche le chargement de la
              structure principale de l’application.
            </p>

            <div className="gc-fatal-card__diagnostic">
              <div>
                <span>MESSAGE</span>
                <strong>
                  {error.message || "Erreur inconnue"}
                </strong>
              </div>

              <div>
                <span>DIGEST</span>
                <strong>
                  {error.digest || "Non disponible"}
                </strong>
              </div>
            </div>

            <div className="gc-fatal-card__actions">
              <button
                type="button"
                onClick={reset}
              >
                Relancer l’application
              </button>

              <button
                type="button"
                className="is-secondary"
                onClick={() => window.location.reload()}
              >
                Rechargement complet
              </button>
            </div>
          </section>
        </main>
      </body>
    </html>
  );
}
