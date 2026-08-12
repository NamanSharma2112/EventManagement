"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { SeatLegend, SeatMap } from "@/components/SeatMap";
import {
  Alert,
  Button,
  Card,
  Field,
  SeatSkeleton,
  Spinner,
  inputClass,
} from "@/components/ui";
import { useSeatMap } from "@/hooks/useSeatMap";
import {
  ApiError,
  createBooking,
  formatEventDate,
  formatPrice,
  type Booking,
  type Seat,
} from "@/lib/api";

type Feedback =
  | { kind: "success"; booking: Booking }
  | { kind: "conflict"; message: string; seatIds: number[] }
  | { kind: "error"; message: string }
  | null;

export function EventBooking({ eventId }: { eventId: number }) {
  const { data: seatMap, loading, refreshing, error, refresh } = useSeatMap(eventId);

  const [pickedIds, setPickedIds] = useState<number[]>([]);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState<Feedback>(null);

  const seatsById = useMemo(() => {
    const map = new Map<number, Seat>();
    seatMap?.rows.forEach((row) => row.seats.forEach((seat) => map.set(seat.id, seat)));
    return map;
  }, [seatMap]);

  /**
   * The selection is derived from the live seat map rather than stored, so a
   * seat that somebody else booked between polls simply stops counting as
   * selected -- no effect, and no way for the two to disagree.
   */
  const selected = useMemo(
    () =>
      pickedIds
        .map((id) => seatsById.get(id))
        .filter((seat): seat is Seat => seat?.status === "AVAILABLE")
        .sort((a, b) => a.row_index - b.row_index || a.seat_number - b.seat_number),
    [pickedIds, seatsById],
  );

  /** Seats the user had picked that are no longer theirs to take. */
  const lost = useMemo(
    () =>
      pickedIds
        .map((id) => seatsById.get(id))
        .filter((seat): seat is Seat => seat !== undefined && seat.status !== "AVAILABLE"),
    [pickedIds, seatsById],
  );

  const selectedIds = useMemo(() => new Set(selected.map((s) => s.id)), [selected]);
  const total = selected.reduce((sum, seat) => sum + seat.price_cents, 0);

  function toggleSeat(seat: Seat) {
    setFeedback(null);
    setPickedIds((current) =>
      current.includes(seat.id)
        ? current.filter((id) => id !== seat.id)
        : [...current, seat.id],
    );
  }

  function dropLostSeats() {
    const lostIds = new Set(lost.map((seat) => seat.id));
    setPickedIds((current) => current.filter((id) => !lostIds.has(id)));
  }

  async function submit(formEvent: React.FormEvent) {
    formEvent.preventDefault();
    if (selected.length === 0 || submitting) return;

    setSubmitting(true);
    setFeedback(null);
    try {
      const booking = await createBooking({
        event_id: eventId,
        seat_ids: selected.map((seat) => seat.id),
        booker_name: name.trim(),
        booker_email: email.trim(),
      });
      setFeedback({ kind: "success", booking });
      setPickedIds([]);
      setName("");
      setEmail("");
    } catch (err) {
      if (err instanceof ApiError && err.isConflict) {
        // Somebody won the race. Name the seats that clashed and pull a fresh
        // map, which will also drop them out of the selection.
        setFeedback({
          kind: "conflict",
          message: err.message,
          seatIds: err.conflictingSeats.map((seat) => seat.seat_id),
        });
      } else {
        setFeedback({
          kind: "error",
          message:
            err instanceof ApiError
              ? err.message
              : "The booking could not be completed.",
        });
      }
    } finally {
      setSubmitting(false);
      refresh();
    }
  }

  if (loading) {
    return (
      <div className="space-y-6">
        <Spinner label="Loading seat map" />
        <Card>
          <SeatSkeleton />
        </Card>
      </div>
    );
  }

  if (!seatMap) {
    return (
      <div className="space-y-4">
        <Alert tone="danger" title="Could not load this event">
          {error ?? "This event does not exist."}
        </Alert>
        <Link href="/" className="text-sm text-primary underline">
          Back to all events
        </Link>
      </div>
    );
  }

  const { event } = seatMap;
  const conflictIds = feedback?.kind === "conflict" ? feedback.seatIds : [];

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Link href="/" className="text-sm text-muted hover:text-ink">
            &larr; All events
          </Link>
          <h1 className="mt-1 display-lg text-ink">{event.name}</h1>
          <p className="mt-1 text-sm text-muted">
            {formatEventDate(event.event_date)}
            {event.venue && ` - ${event.venue}`}
          </p>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <span className="tabular-nums text-muted">
            <span className="font-semibold text-ink">
              {seatMap.available_seats}
            </span>{" "}
            of {seatMap.total_seats} free
          </span>
          <Button variant="secondary" onClick={refresh} disabled={refreshing}>
            {refreshing ? "Refreshing..." : "Refresh"}
          </Button>
        </div>
      </header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <Card className="self-start">
          <SeatMap
            seatMap={seatMap}
            selectedIds={selectedIds}
            conflictIds={conflictIds}
            onToggleSeat={toggleSeat}
            disabled={submitting}
          />
          <SeatLegend className="mt-6 border-t border-hairline pt-4" />
        </Card>

        <div className="space-y-4 lg:sticky lg:top-20 lg:self-start">
          {feedback?.kind === "success" && (
            <Alert tone="success" title="Booking confirmed">
              <p>
                {feedback.booking.seats.map((s) => s.label).join(", ")} booked for{" "}
                {feedback.booking.booker_name}.
              </p>
              <p className="mt-2">
                Reference{" "}
                <Link
                  href={`/bookings/${feedback.booking.reference}`}
                  className="font-mono font-semibold underline"
                >
                  {feedback.booking.reference}
                </Link>
              </p>
            </Alert>
          )}

          {feedback?.kind === "conflict" && (
            <Alert tone="warning" title="Those seats just went">
              {feedback.message}
            </Alert>
          )}

          {feedback?.kind === "error" && (
            <Alert tone="danger" title="Booking failed">
              {feedback.message}
            </Alert>
          )}

          {lost.length > 0 && (
            <Alert tone="warning" title="Seats taken while you were choosing">
              <p>
                {lost.map((s) => s.label).join(", ")}{" "}
                {lost.length === 1 ? "is" : "are"} no longer available, so{" "}
                {lost.length === 1 ? "it has" : "they have"} been left out of your
                selection.
              </p>
              <Button
                variant="ghost"
                className="mt-2 px-0"
                onClick={dropLostSeats}
                type="button"
              >
                Dismiss
              </Button>
            </Alert>
          )}

          <Card>
            <h2 className="display-sm text-ink">Your selection</h2>

            {selected.length === 0 ? (
              <p className="mt-2 text-sm text-muted">
                Pick one or more available seats on the map. You can select
                several before confirming.
              </p>
            ) : (
              <>
                <ul className="mt-3 space-y-1.5">
                  {selected.map((seat) => (
                    <li
                      key={seat.id}
                      className="flex items-center justify-between gap-2 rounded-sm bg-surface-strong px-3 py-1.5 text-sm"
                    >
                      <span>
                        <span className="font-semibold">{seat.label}</span>
                        <span className="ml-2 text-xs text-muted">
                          {seat.section_name}
                        </span>
                      </span>
                      <span className="flex items-center gap-2">
                        <span className="tabular-nums text-muted">
                          {formatPrice(seat.price_cents)}
                        </span>
                        <button
                          type="button"
                          onClick={() => toggleSeat(seat)}
                          aria-label={`Remove seat ${seat.label}`}
                          className="rounded px-1 text-muted transition hover:text-error"
                        >
                          &times;
                        </button>
                      </span>
                    </li>
                  ))}
                </ul>
                <div className="mt-3 flex justify-between border-t border-hairline pt-3 text-sm font-semibold">
                  <span>
                    Total ({selected.length} seat{selected.length === 1 ? "" : "s"})
                  </span>
                  <span className="tabular-nums">{formatPrice(total)}</span>
                </div>
              </>
            )}
          </Card>

          <Card>
            <h2 className="display-sm text-ink">Your details</h2>
            <form onSubmit={submit} className="mt-3 space-y-3">
              <Field label="Name">
                <input
                  className={inputClass}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Ada Lovelace"
                  required
                  maxLength={120}
                  autoComplete="name"
                />
              </Field>
              <Field label="Email">
                <input
                  className={inputClass}
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="ada@example.com"
                  required
                  autoComplete="email"
                />
              </Field>
              <Button
                type="submit"
                className="w-full"
                disabled={selected.length === 0 || submitting}
              >
                {submitting
                  ? "Confirming..."
                  : selected.length === 0
                    ? "Select a seat first"
                    : `Confirm ${selected.length} seat${selected.length === 1 ? "" : "s"}`}
              </Button>
              <p className="text-xs text-muted">
                If someone books one of your seats first, the whole request is
                rejected and nothing is booked.
              </p>
            </form>
          </Card>
        </div>
      </div>
    </div>
  );
}
