"use client";

import Link from "next/link";
import { useCallback } from "react";

import { usePolledResource } from "@/hooks/usePolledResource";
import { Alert, EmptyState, Spinner } from "@/components/ui";
import { formatEventDate, listEvents } from "@/lib/api";

export default function EventsPage() {
  const fetcher = useCallback(() => listEvents(), []);
  const { data: events, loading, error } = usePolledResource(fetcher, {
    fallbackMessage: "Could not load events.",
  });

  return (
    <div className="space-y-8">
      <header>
        <h1 className="display-xl text-ink">Upcoming events</h1>
        <p className="mt-1 text-base text-muted">
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

      {/* Card grid, marketplace-dense: 16px gutters, columns drop cleanly. */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {events?.map((event) => {
          const soldOut = event.available_seats === 0;
          const takenPercent = event.total_seats
            ? Math.round(
                ((event.booked_seats + event.blocked_seats) / event.total_seats) * 100,
              )
            : 0;

          return (
            <Link
              key={event.id}
              href={`/events/${event.id}`}
              className="group flex flex-col gap-4 rounded-md border border-hairline bg-canvas p-5 transition hover:shadow-tier"
            >
              <div className="flex-1">
                <div className="flex items-start justify-between gap-3">
                  <h2 className="title-md text-ink">{event.name}</h2>
                  {soldOut && (
                    <span className="shrink-0 rounded-full border border-hairline bg-surface-strong px-2.5 py-1 text-[11px] font-semibold text-muted">
                      Sold out
                    </span>
                  )}
                </div>
                <p className="mt-1.5 text-sm text-muted">
                  {formatEventDate(event.event_date)}
                </p>
                {event.venue && (
                  <p className="text-sm text-muted">{event.venue}</p>
                )}
                {event.description && (
                  <p className="mt-2 line-clamp-2 text-sm text-body">
                    {event.description}
                  </p>
                )}
              </div>

              <div>
                <div className="flex justify-between text-sm">
                  <span className="text-ink">
                    <span className="font-semibold tabular-nums">
                      {event.available_seats}
                    </span>{" "}
                    <span className="text-muted">
                      of {event.total_seats} seats free
                    </span>
                  </span>
                  <span className="tabular-nums text-muted">
                    {takenPercent}% taken
                  </span>
                </div>
                <div
                  className="mt-2 h-1 overflow-hidden rounded-full bg-surface-strong"
                  role="progressbar"
                  aria-valuenow={takenPercent}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-label={`${takenPercent} percent of seats taken`}
                >
                  <div
                    className="h-full rounded-full bg-primary transition-[width]"
                    style={{ width: `${takenPercent}%` }}
                  />
                </div>
                <span className="mt-4 inline-flex text-sm font-medium text-ink underline underline-offset-4">
                  {soldOut ? "View seat map" : "Choose seats"}
                </span>
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
