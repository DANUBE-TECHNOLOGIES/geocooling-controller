export default function Loading() {
  return (
    <main
      className="gc-route-loading"
      aria-live="polite"
      aria-busy="true"
    >
      <section>
        <div
          className="gc-route-loading__symbol"
          aria-hidden="true"
        >
          <span />
          <span />
          <span />
        </div>

        <p>
          SMART BUILDING CONTROLLER
        </p>

        <strong>
          Chargement de la console GeoCooling…
        </strong>

        <small>
          Initialisation de la supervision locale
        </small>
      </section>
    </main>
  );
}
