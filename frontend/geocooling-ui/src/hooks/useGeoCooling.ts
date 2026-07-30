"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { fetchGeoCoolingSnapshot } from "@/lib/api";
import type { GeoCoolingSnapshot } from "@/types/geocooling";

const POLLING_INTERVAL_MS = 2000;

export function useGeoCooling() {
  const [snapshot, setSnapshot] = useState<GeoCoolingSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);

  const activeRequest = useRef<AbortController | null>(null);

  const refresh = useCallback(async (initial = false) => {
    activeRequest.current?.abort();

    const controller = new AbortController();

    activeRequest.current = controller;

    if (initial) {
      setLoading(true);
    } else {
      setRefreshing(true);
    }

    try {

      const nextSnapshot = await fetchGeoCoolingSnapshot(
        controller.signal
      );

      setSnapshot(nextSnapshot);

      setLastUpdate(new Date());

      setError(null);

    } catch (cause) {

      if (
        cause instanceof Error &&
        cause.name === "AbortError"
      ) {
        return;
      }

      setError(
        cause instanceof Error
          ? cause.message
          : "Erreur GeoCooling inconnue"
      );

    } finally {

      if (activeRequest.current === controller) {
        setLoading(false);
        setRefreshing(false);
      }

    }

  }, []);

  useEffect(() => {

    const timer = setTimeout(() => {
      void refresh(true);
    }, 0);

    const interval = window.setInterval(() => {
      void refresh(false);
    }, POLLING_INTERVAL_MS);

    return () => {

      clearTimeout(timer);

      clearInterval(interval);

      activeRequest.current?.abort();

    };

  }, [refresh]);

  return {
    snapshot,
    loading,
    refreshing,
    error,
    lastUpdate,
    refresh,
  };
}
