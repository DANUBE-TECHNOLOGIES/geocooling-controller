import Link from "next/link";

export default function NotFound() {
  return (
    <main className="gc-route-state">
      <section className="gc-route-state__card is-not-found">
        <div
          className="gc-route-state__icon"
          aria-hidden="true"
        >
          404
        </div>

        <p className="gc-route-state__eyebrow">
          ROUTE INTROUVABLE
        </p>

        <h1>
          Cette console n’existe pas
        </h1>

        <p>
          L’adresse demandée ne correspond à aucun module de
          l’interface GeoCooling Enterprise.
        </p>

        <div className="gc-route-state__actions">
          <Link href="/">
            Retour au dashboard
          </Link>

          <Link
            href="/runtime"
            className="is-secondary"
          >
            Ouvrir le runtime
          </Link>
        </div>
      </section>
    </main>
  );
}
