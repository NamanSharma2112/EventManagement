"use client";

import { useCallback } from "react";

import { getSeatMap, type SeatMap } from "@/lib/api";
import { usePolledResource, type PolledResource } from "./usePolledResource";

/** How often the seat map is refetched while the tab is visible. */
export const SEAT_MAP_POLL_MS = 5000;

export function useSeatMap(eventId: number): PolledResource<SeatMap> {
  const fetcher = useCallback(() => getSeatMap(eventId), [eventId]);
  return usePolledResource(fetcher, {
    intervalMs: SEAT_MAP_POLL_MS,
    fallbackMessage: "Could not load the seat map.",
  });
}
