export class GeoCoolingAPI {
  private static async get<T>(
    path: string,
    signal?: AbortSignal,
  ): Promise<T> {
    const response = await fetch(`/api/geocooling/${path}`, {
      cache: "no-store",
      signal,
      headers: {
        Accept: "application/json",
      },
    });

    if (!response.ok) {
      throw new Error(
        `GeoCooling API (${response.status})`
      );
    }

    return response.json() as Promise<T>;
  }

  static dashboard(signal?: AbortSignal) {
    return this.get("dashboard", signal);
  }

  static brain(signal?: AbortSignal) {
    return this.get("brain/dashboard", signal);
  }

  static historian(signal?: AbortSignal) {
    return this.get("historian/latest", signal);
  }

  static forecast(signal?: AbortSignal) {
    return this.get("brain/forecast", signal);
  }

  static digitalTwin(signal?: AbortSignal) {
    return this.get("digital-twin", signal);
  }

  static runtime(signal?: AbortSignal) {
    return this.get("runtime", signal);
  }

  static alarms(signal?: AbortSignal) {
    return this.get("alarms", signal);
  }

  static readiness(signal?: AbortSignal) {
    return this.get("readiness", signal);
  }

  static health(signal?: AbortSignal) {
    return this.get("health", signal);
  }

  static realtime(signal?: AbortSignal) {
    return this.get("realtime-metrics", signal);
  }

  static events(signal?: AbortSignal) {
    return this.get("events/latest", signal);
  }
}
