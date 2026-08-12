"use client";

import Link from "next/link";
import { useCallback } from "react";

import { CreateEventForm } from "./CreateEventForm";
import { RequireAuth } from "@/components/RequireAuth";
import { usePolledResource } from "@/hooks/usePolledResource";
import { Alert, Card, Spinner, StatTile } from "@/components/ui";
import { formatEventDate, listEvents } from "@/lib/api";

export default function AdminPage() {
  return (
    <RequireAuth adminOnly redirectTo="/admin">
      <AdminContent />
    </RequireAuth>
  );
}

function AdminContent() {
  const fetcher = useCallback(() => listEvents(), []);
  const { data: events, loading, error, refresh } = usePolledResource(fetcher, {
    fallbackMessage: "Could not load events.",
  });

  const totals = (events ?? []).reduce(
    (acc, event) => ({
      seats: acc.seats + event.total_seats,
      booked: acc.booked + event.booked_seats,
    }),
    { seats: 0, booked: 0 },
  );

  return (
    <div className="space-y-8">
      <header>
        <h1 className="display-xl text-ink">Admin</h1>
        <p className="mt-1 text-sm text-muted">
          Create events and their seat layouts, then open an event to block
          seats and watch bookings come in. Every write here is checked against
          an admin token on the API, not just hidden in the UI.
        </p>
      </header>

      {error && (
        <Alert tone="danger" title="Something went wrong">
          {error}
        </Alert>
      )}

      <section className="space-y-4">
        <h2 className="display-sm text-ink">Events</h2>

        {loading && <Spinner label="Loading events" />}

        {events && events.length > 0 && (
          <div className="grid gap-3 sm:grid-cols-3">
            <StatTile label="Events" value={events.length} />
            <StatTile label="Seats configured" value={totals.seats} />
            <StatTile label="Seats booked" value={totals.booked} tone="accent" />
          </div>
        )}

        {events?.length === 0 && (
          <Card>
            <p className="text-sm text-muted">
              No events yet. Create the first one below.
            </p>
          </Card>
        )}

        <div className="space-y-2">
          {events?.map((event) => (
            <Link
              key={event.id}
              href={`/admin/events/${event.id}`}
              className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-hairline bg-canvas px-5 py-4 transition hover:border-ink"
            >
              <div>
                <p className="font-medium">{event.name}</p>
                <p className="mt-0.5 text-sm text-muted">
                  {formatEventDate(event.event_date)}
                  {event.venue && ` - ${event.venue}`} - {event.row_count} rows &times;{" "}
                  {event.column_count}
                </p>
              </div>
              <div className="flex items-center gap-5 text-sm tabular-nums">
                <span className="text-muted">
                  <span className="font-semibold text-ink">
                    {event.booked_seats}
                  </span>{" "}
                  booked
                </span>
                <span className="text-muted">
                  <span className="font-semibold text-ink">
                    {event.available_seats}
                  </span>{" "}
                  free
                </span>
                <span aria-hidden className="text-muted">
                  &rarr;
                </span>
              </div>
            </Link>
          ))}
        </div>
      </section>

      <section className="space-y-4">
        <h2 className="display-sm text-ink">Create an event</h2>
        <CreateEventForm onCreated={refresh} />
      </section>
    </div>
  );
}
