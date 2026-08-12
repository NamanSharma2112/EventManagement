"use client";

import Link from "next/link";
import { useCallback, useState } from "react";

import { usePolledResource } from "@/hooks/usePolledResource";
import { Alert, Button, Card, Spinner, StatusPill } from "@/components/ui";
import {
  ApiError,
  cancelBooking,
  formatPrice,
  formatTimestamp,
  getBooking,
  type Booking,
} from "@/lib/api";

export function BookingDetail({ reference }: { reference: string }) {
  const fetcher = useCallback(() => getBooking(reference), [reference]);
  const { data: fetched, loading, error } = usePolledResource(fetcher, {
    fallbackMessage: "Could not load that booking.",
  });

  // Set only once the user cancels, so the page reflects the new state without
  // waiting for a refetch.
  const [cancelledBooking, setCancelledBooking] = useState<Booking | null>(null);
  const [cancelError, setCancelError] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [confirmingCancel, setConfirmingCancel] = useState(false);

  const booking = cancelledBooking ?? fetched;

  async function doCancel() {
    setCancelling(true);
    setCancelError(null);
    try {
      setCancelledBooking(await cancelBooking(reference));
      setConfirmingCancel(false);
    } catch (err) {
      setCancelError(
        err instanceof ApiError ? err.message : "Could not cancel that booking.",
      );
    } finally {
      setCancelling(false);
    }
  }

  if (loading) {
    return <Spinner label="Loading booking" />;
  }

  if (!booking) {
    return (
      <div className="mx-auto max-w-md space-y-4">
        <Alert tone="danger" title="Booking not found">
          {error ?? `No booking found with reference ${reference}.`}
        </Alert>
        <Link href="/bookings" className="text-sm text-primary underline">
          Try another reference
        </Link>
      </div>
    );
  }

  const cancelled = booking.status === "CANCELLED";

  return (
    <div className="mx-auto max-w-xl space-y-4">
      <Link href="/" className="text-sm text-muted hover:text-ink">
        &larr; All events
      </Link>

      {!cancelled && (
        <Alert tone="success" title="Your seats are confirmed">
          A confirmation for {booking.booker_email} is logged by the API (mock
          email -- nothing is actually sent).
        </Alert>
      )}

      {cancelError && <Alert tone="danger">{cancelError}</Alert>}

      <Card className="space-y-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-wide text-muted">Reference</p>
            <p className="font-mono text-xl font-semibold">{booking.reference}</p>
          </div>
          <StatusPill status={booking.status} />
        </div>

        <div className="border-t border-hairline pt-4">
          <h1 className="display-sm text-ink">{booking.event_name}</h1>
          <p className="mt-1 text-sm text-muted">
            Booked {formatTimestamp(booking.created_at)}
            {booking.cancelled_at &&
              ` - cancelled ${formatTimestamp(booking.cancelled_at)}`}
          </p>
        </div>

        <dl className="grid grid-cols-2 gap-4 border-t border-hairline pt-4 text-sm">
          <div>
            <dt className="text-muted">Name</dt>
            <dd className="mt-0.5 font-medium">{booking.booker_name}</dd>
          </div>
          <div>
            <dt className="text-muted">Email</dt>
            <dd className="mt-0.5 break-all font-medium">{booking.booker_email}</dd>
          </div>
        </dl>

        <div className="border-t border-hairline pt-4">
          <p className="text-sm text-muted">
            {booking.seats.length} seat{booking.seats.length === 1 ? "" : "s"}
          </p>
          <ul className="mt-2 space-y-1.5">
            {booking.seats.map((seat) => (
              <li
                key={seat.seat_id}
                className={`flex items-center justify-between rounded-sm bg-surface-strong px-3 py-2 text-sm ${
                  cancelled ? "opacity-60" : ""
                }`}
              >
                <span>
                  <span className="font-semibold">{seat.label}</span>
                  <span className="ml-2 text-xs text-muted">{seat.section_name}</span>
                </span>
                <span className="tabular-nums text-muted">
                  {formatPrice(seat.price_cents)}
                </span>
              </li>
            ))}
          </ul>
          <div className="mt-3 flex justify-between border-t border-hairline pt-3 font-semibold">
            <span>Total</span>
            <span className="tabular-nums">
              {formatPrice(booking.total_amount_cents)}
            </span>
          </div>
        </div>

        {!cancelled && (
          <div className="border-t border-hairline pt-4">
            {confirmingCancel ? (
              <div className="space-y-3">
                <p className="text-sm text-muted">
                  Cancelling releases {booking.seats.map((s) => s.label).join(", ")}{" "}
                  back to other bookers. This cannot be undone.
                </p>
                <div className="flex gap-2">
                  <Button variant="danger" onClick={doCancel} disabled={cancelling}>
                    {cancelling ? "Cancelling..." : "Yes, cancel booking"}
                  </Button>
                  <Button
                    variant="ghost"
                    onClick={() => setConfirmingCancel(false)}
                    disabled={cancelling}
                  >
                    Keep it
                  </Button>
                </div>
              </div>
            ) : (
              <Button variant="secondary" onClick={() => setConfirmingCancel(true)}>
                Cancel this booking
              </Button>
            )}
          </div>
        )}

        {cancelled && (
          <p className="border-t border-hairline pt-4 text-sm text-muted">
            These seats have been released and are available to book again.
          </p>
        )}
      </Card>

      <Link
        href={`/events/${booking.event_id}`}
        className="inline-block text-sm text-primary underline"
      >
        Back to the seat map for {booking.event_name}
      </Link>
    </div>
  );
}
