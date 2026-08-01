"use client";

import React from "react";

type ErrorBoundaryProps = {
  children: React.ReactNode;
};

type ErrorBoundaryState = {
  error: Error | null;
  eventId: string | null;
};

function createEventId(): string {
  return [
    "GC",
    Date.now().toString(36).toUpperCase(),
    Math.random().toString(36).slice(2, 8).toUpperCase(),
  ].join("-");
}

export class ErrorBoundary extends React.Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  public state: ErrorBoundaryState = {
    error: null,
    eventId: null,
  };

  public static getDerivedStateFromError(
    error: Error,
  ): ErrorBoundaryState {
    return {
      error,
      eventId: createEventId(),
    };
  }

  public componentDidCatch(
    error: Error,
    info: React.ErrorInfo,
  ): void {
    console.error(
      "[GeoCooling UI] Component failure",
      {
        error,
        componentStack: info.componentStack,
        eventId: this.state.eventId,
      },
    );
  }

  private reset = (): void => {
    this.setState({
      error: null,
      eventId: null,
    });
  };

  private reload = (): void => {
    window.location.reload();
  };

  public render(): React.ReactNode {
    const { error, eventId } = this.state;

    if (!error) {
      return this.props.children;
    }

    return (
      <main className="gc-fatal-shell">
        <section
          className="gc-fatal-card"
          role="alert"
          aria-live="assertive"
        >
          <div
            className="gc-fatal-card__icon"
            aria-hidden="true"
          >
            !
          </div>

          <p className="gc-fatal-card__eyebrow">
            ERREUR DE RENDU
          </p>

          <h1>
            L’interface GeoCooling a rencontré une erreur
          </h1>

          <p className="gc-fatal-card__description">
            Le contrôleur physique n’est pas modifié par cette
            erreur d’affichage. Rechargez la vue ou tentez de
            réinitialiser uniquement les composants de
            l’interface.
          </p>

          <div className="gc-fatal-card__diagnostic">
            <div>
              <span>IDENTIFIANT</span>
              <strong>{eventId ?? "NON DISPONIBLE"}</strong>
            </div>

            <div>
              <span>MESSAGE</span>
              <strong>
                {error.message || "Erreur JavaScript inconnue"}
              </strong>
            </div>
          </div>

          <div className="gc-fatal-card__actions">
            <button
              type="button"
              onClick={this.reset}
            >
              Réinitialiser la vue
            </button>

            <button
              type="button"
              className="is-secondary"
              onClick={this.reload}
            >
              Recharger l’application
            </button>
          </div>

          <small>
            Aucune commande MQTT ou Modbus n’est exécutée par
            cette procédure.
          </small>
        </section>
      </main>
    );
  }
}
