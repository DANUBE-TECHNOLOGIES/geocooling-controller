"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

type ResourceLoader<T> = (
  signal?: AbortSignal
) => Promise<T>;

type GeoCoolingResourceOptions = {
  intervalMs?: number;
  enabled?: boolean;
};

export type GeoCoolingResourceState<T> = {
  data: T | null;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  lastUpdate: Date | null;
  refresh: () => Promise<void>;
};

export function useGeoCoolingResource<T>(
  loader: ResourceLoader<T>,
  options: GeoCoolingResourceOptions = {}
): GeoCoolingResourceState<T> {
  const {
    intervalMs = 5_000,
    enabled = true,
  } = options;

  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(enabled);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(
    null
  );

  const activeRequest =
    useRef<AbortController | null>(null);

  const mounted = useRef(true);

  const load = useCallback(
    async (initial: boolean): Promise<void> => {
      activeRequest.current?.abort();

      const controller = new AbortController();
      activeRequest.current = controller;

      if (initial) {
        setLoading(true);
      } else {
        setRefreshing(true);
      }

      try {
        const response = await loader(controller.signal);

        if (!mounted.current) {
          return;
        }

        setData(response);
        setError(null);
        setLastUpdate(new Date());
      } catch (cause) {
        if (
          cause instanceof Error &&
          cause.name === "AbortError"
        ) {
          return;
        }

        if (!mounted.current) {
          return;
        }

        setError(
          cause instanceof Error
            ? cause.message
            : "Erreur GeoCooling inconnue"
        );
      } finally {
        if (
          mounted.current &&
          activeRequest.current === controller
        ) {
          setLoading(false);
          setRefreshing(false);
        }
      }
    },
    [loader]
  );

  const refresh = useCallback(async (): Promise<void> => {
    await load(false);
  }, [load]);

  useEffect(() => {
    mounted.current = true;

    if (!enabled) {
      return () => {
        mounted.current = false;
        activeRequest.current?.abort();
      };
    }

    const initialTimer = window.setTimeout(() => {
      void load(true);
    }, 0);

    const pollingTimer = window.setInterval(() => {
      void load(false);
    }, intervalMs);

    return () => {
      mounted.current = false;
      window.clearTimeout(initialTimer);
      window.clearInterval(pollingTimer);
      activeRequest.current?.abort();
    };
  }, [enabled, intervalMs, load]);

  return {
    data,
    loading,
    refreshing,
    error,
    lastUpdate,
    refresh,
  };
}
