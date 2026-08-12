"use client";

import Link from "next/link";
import { useCallback } from "react";

import { usePolledResource } from "@/hooks/usePolledResource";
import { Alert, Card, EmptyState, Spinner } from "@/components/ui";
import { formatEventDate, listEvents } from "@/lib/api";

export default function EventsPage() {
  const fetcher = useCallback(() => listEvents(), []);
  const { data: events, loading, error } = usePolledResource(fetcher, {
    fallbackMessage: "Could not load events.",
  });

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Upcoming events</h1>
        <p className="mt-1 text-sm text-muted">
          Pick an event to see its seat map and book seats.
        </p>
      </header>

      {error && (
        <Alert tone="danger" title="Something went wrong">
          {error}
        </Alert>
      )}

      {loading && <Spinner label="Loading events" />}

      {events?.length === 0 && (
        <EmptyState
          title="No events yet"
          action={{ href: "/admin", label: "Create one in Admin" }}
        >
          An admin needs to create an event and its seat layout first.
        </EmptyState>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        {events?.map((event) => {
          const soldOut = event.available_seats === 0;
          const takenPercent = event.total_seats
            ? Math.round(
                ((event.booked_seats + event.blocked_seats) / event.total_seats) * 100,
              )
            : 0;

          return (
            <Card key={event.id} className="flex flex-col justify-between gap-4">
              <div>
                <div className="flex items-start justify-between gap-3">
                  <h2 className="text-lg font-semibold leading-tight">{event.name}</h2>
                  {soldOut && (
                    <span className="shrink-0 rounded-full border border-line-strong bg-surface-muted px-2 py-0.5 text-xs font-medium text-muted">
                      Sold out
                    </span>
                  )}
                </div>
                <p className="mt-1 text-sm text-muted">
                  {formatEventDate(event.event_date)}
                  {event.venue && ` - ${event.venue}`}
                </p>
                {event.description && (
                  <p className="mt-2 line-clamp-2 text-sm text-muted">
                    {event.description}
                  </p>
                )}
              </div>

              <div className="space-y-3">
                <div>
                  <div className="flex justify-between text-xs text-muted">
                    <span>
                      <span className="font-semibold text-foreground tabular-nums">
                        {event.available_seats}
                      </span>{" "}
                      of {event.total_seats} seats free
                    </span>
                    <span className="tabular-nums">{takenPercent}% taken</span>
                  </div>
                  <div
                    className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-surface-muted"
                    role="progressbar"
                    aria-valuenow={takenPercent}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-label={`${takenPercent} percent of seats taken`}
                  >
                    <div
                      className="h-full rounded-full bg-accent transition-[width]"
                      style={{ width: `${takenPercent}%` }}
                    />
                  </div>
                </div>

                <Link
                  href={`/events/${event.id}`}
                  className="inline-flex w-full items-center justify-center rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-contrast transition hover:opacity-90"
                >
                  {soldOut ? "View seat map" : "Choose seats"}
                </Link>
              </div>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
