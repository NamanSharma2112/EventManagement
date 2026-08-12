"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "@/lib/api";

export interface PolledResource<T> {
  data: T | null;
  /** True only until the first response arrives, so polling never flashes the UI. */
  loading: boolean;
  /** True while a background or user-triggered refresh is in flight. */
  refreshing: boolean;
  error: string | null;
  refresh: () => void;
}

/**
 * Fetches a resource and keeps it fresh.
 *
 * The assignment only asks that other users see a booking after a refresh, so
 * this polls on an interval and refetches when the tab regains focus, rather
 * than opening a WebSocket. Polling pauses while the tab is hidden.
 *
 * `fetcher` must be stable -- wrap it in `useCallback` in the caller.
 */
export function usePolledResource<T>(
  fetcher: () => Promise<T>,
  {
    intervalMs = 0,
    fallbackMessage = "Something went wrong.",
  }: { intervalMs?: number; fallbackMessage?: string } = {},
): PolledResource<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Assigned inside the effect (never during render) so `refresh` can reach the
  // current fetch without re-subscribing.
  const runRef = useRef<() => Promise<void>>(async () => {});
  const hasDataRef = useRef(false);

  useEffect(() => {
    let cancelled = false;

    const run = async () => {
      try {
        const result = await fetcher();
        if (cancelled) return;
        hasDataRef.current = true;
        setData(result);
        setError(null);
      } catch (err) {
        if (cancelled) return;
        // A failed poll must not wipe data that is already on screen; only
        // surface the error when there is nothing to show.
        if (!hasDataRef.current) {
          setError(err instanceof ApiError ? err.message : fallbackMessage);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    runRef.current = run;
    run();

    if (intervalMs <= 0) {
      return () => {
        cancelled = true;
      };
    }

    const poll = () => {
      if (document.visibilityState === "visible") run();
    };
    const timer = setInterval(poll, intervalMs);
    window.addEventListener("focus", poll);
    document.addEventListener("visibilitychange", poll);

    return () => {
      cancelled = true;
      clearInterval(timer);
      window.removeEventListener("focus", poll);
      document.removeEventListener("visibilitychange", poll);
    };
  }, [fetcher, intervalMs, fallbackMessage]);

  const refresh = useCallback(() => {
    setRefreshing(true);
    runRef.current().finally(() => setRefreshing(false));
  }, []);

  return { data, loading, refreshing, error, refresh };
}
