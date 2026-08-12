"use client";

import Link from "next/link";
import { useCallback, useMemo, useState } from "react";

import { SeatLegend, SeatMap } from "@/components/SeatMap";
import {
  Alert,
  Button,
  Card,
  SeatSkeleton,
  Spinner,
  StatTile,
  StatusPill,
} from "@/components/ui";
import { usePolledResource } from "@/hooks/usePolledResource";
import { SEAT_MAP_POLL_MS, useSeatMap } from "@/hooks/useSeatMap";
import {
  ApiError,
  formatEventDate,
  formatPrice,
  formatTimestamp,
  getAdminSummary,
  setSeatsBlocked,
  type Seat,
} from "@/lib/api";

export function AdminEventDashboard({ eventId }: { eventId: number }) {
  const { data: seatMap, loading, refreshing, error, refresh } = useSeatMap(eventId);

  const summaryFetcher = useCallback(() => getAdminSummary(eventId), [eventId]);
  const {
    data: summary,
    error: summaryError,
    refresh: refreshSummary,
  } = usePolledResource(summaryFetcher, {
    intervalMs: SEAT_MAP_POLL_MS,
    fallbackMessage: "Could not load the dashboard.",
  });

  const [pickedSeatIds, setPickedSeatIds] = useState<number[]>([]);
  const [reason, setReason] = useState("");
  const [working, setWorking] = useState(false);
  const [notice, setNotice] = useState<{
    tone: "success" | "warning" | "danger";
    text: string;
  } | null>(null);

  const seatsById = useMemo(() => {
    const map = new Map<number, Seat>();
    seatMap?.rows.forEach((row) => row.seats.forEach((seat) => map.set(seat.id, seat)));
    return map;
  }, [seatMap]);

  // Derived from the live map, so a seat booked while it was selected drops out
  // of the selection on the next poll instead of going stale.
  const picked = useMemo(
    () =>
      pickedSeatIds
        .map((id) => seatsById.get(id))
        .filter((seat): seat is Seat => seat !== undefined && seat.status !== "BOOKED")
        .sort((a, b) => a.row_index - b.row_index || a.seat_number - b.seat_number),
    [pickedSeatIds, seatsById],
  );

  const pickedIds = useMemo(() => new Set(picked.map((s) => s.id)), [picked]);

  /**
   * The admin map lets any non-booked seat be picked, so blocking and
   * unblocking use the same selection. Booked seats stay untouchable -- the API
   * refuses to block them anyway.
   */
  function togglePick(seat: Seat) {
    if (seat.status === "BOOKED") return;
    setNotice(null);
    setPickedSeatIds((current) =>
      current.includes(seat.id)
        ? current.filter((id) => id !== seat.id)
        : [...current, seat.id],
    );
  }

  async function applyBlock(blocked: boolean) {
    const targets = picked.filter((seat) =>
      blocked ? seat.status === "AVAILABLE" : seat.status === "BLOCKED",
    );
    if (targets.length === 0) return;

    setWorking(true);
    setNotice(null);
    try {
      const result = await setSeatsBlocked(eventId, {
        seat_ids: targets.map((s) => s.id),
        blocked,
        reason: blocked ? reason.trim() || null : null,
      });
      const verb = blocked ? "blocked" : "unblocked";
      const skipped = result.skipped_booked_seat_ids.length;
      setNotice({
        tone: skipped ? "warning" : "success",
        text:
          `${result.updated_seat_ids.length} seat(s) ${verb}.` +
          (skipped ? ` ${skipped} already booked and left alone.` : ""),
      });
      setPickedSeatIds([]);
      setReason("");
    } catch (err) {
      setNotice({
        tone: "danger",
        text: err instanceof ApiError ? err.message : "Could not update those seats.",
      });
    } finally {
      setWorking(false);
      refresh();
      refreshSummary();
    }
  }

  if (loading) {
    return (
      <div className="space-y-6">
        <Spinner label="Loading dashboard" />
        <Card>
          <SeatSkeleton />
        </Card>
      </div>
    );
  }

  if (error && !seatMap) {
    return (
      <div className="space-y-4">
        <Alert tone="danger" title="Could not load this event">
          {error}
        </Alert>
        <Link href="/admin" className="text-sm text-primary underline">
          Back to admin
        </Link>
      </div>
    );
  }

  if (!seatMap) return null;
  const { event } = seatMap;

  const pickedBlocked = picked.filter((s) => s.status === "BLOCKED").length;
  const pickedAvailable = picked.length - pickedBlocked;

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Link href="/admin" className="text-sm text-muted hover:text-ink">
            &larr; Admin
          </Link>
          <h1 className="mt-1 display-lg text-ink">{event.name}</h1>
          <p className="mt-1 text-sm text-muted">
            {formatEventDate(event.event_date)}
            {event.venue && ` - ${event.venue}`} - {event.row_count} rows &times;{" "}
            {event.column_count} seats
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link
            href={`/events/${event.id}`}
            className="rounded-sm border border-hairline px-4 py-2 text-sm font-medium transition hover:border-ink"
          >
            Open booking page
          </Link>
          <Button
            variant="secondary"
            onClick={() => {
              refresh();
              refreshSummary();
            }}
            disabled={refreshing}
          >
            {refreshing ? "Refreshing..." : "Refresh"}
          </Button>
        </div>
      </header>

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <StatTile label="Total seats" value={seatMap.total_seats} />
        <StatTile label="Booked" value={seatMap.booked_seats} tone="accent" />
        <StatTile label="Available" value={seatMap.available_seats} tone="success" />
        <StatTile label="Blocked" value={seatMap.blocked_seats} />
        <StatTile
          label="Revenue"
          value={summary ? formatPrice(summary.revenue_cents) : "-"}
        />
      </section>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <Card className="self-start">
          <h2 className="mb-4 display-sm">Seat map</h2>
          <SeatMap
            seatMap={seatMap}
            selectedIds={pickedIds}
            onToggleSeat={togglePick}
            disabled={working}
            isSelectable={(seat) => seat.status !== "BOOKED"}
          />
          <SeatLegend className="mt-6 border-t border-hairline pt-4" />
          <p className="mt-3 text-xs text-muted">
            Click any seat that is not booked to select it, then block or unblock
            the selection. Blocked seats stay unbookable until you release them.
          </p>
        </Card>

        <div className="space-y-4 lg:sticky lg:top-20 lg:self-start">
          {notice && <Alert tone={notice.tone}>{notice.text}</Alert>}

          <Card>
            <h2 className="display-sm text-ink">Block seats</h2>
            {picked.length === 0 ? (
              <p className="mt-2 text-sm text-muted">
                Select seats on the map to hold them back for VIPs, or to release
                seats you blocked earlier.
              </p>
            ) : (
              <div className="mt-3 space-y-3">
                <p className="text-sm">
                  <span className="font-semibold tabular-nums">{picked.length}</span>{" "}
                  selected:{" "}
                  <span className="text-muted">
                    {picked
                      .slice()
                      .sort(
                        (a, b) =>
                          a.row_index - b.row_index || a.seat_number - b.seat_number,
                      )
                      .map((s) => s.label)
                      .join(", ")}
                  </span>
                </p>
                <input
                  className="w-full rounded-sm border border-hairline bg-canvas px-3 py-2 text-sm placeholder:text-muted focus:border-ink focus:outline-none"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="Reason (optional): VIP hold, sound desk..."
                  maxLength={255}
                />
                <div className="flex flex-wrap gap-2">
                  <Button
                    onClick={() => applyBlock(true)}
                    disabled={working || pickedAvailable === 0}
                  >
                    Block {pickedAvailable > 0 ? pickedAvailable : ""}
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={() => applyBlock(false)}
                    disabled={working || pickedBlocked === 0}
                  >
                    Unblock {pickedBlocked > 0 ? pickedBlocked : ""}
                  </Button>
                  <Button
                    variant="ghost"
                    onClick={() => setPickedSeatIds([])}
                    disabled={working}
                  >
                    Clear
                  </Button>
                </div>
              </div>
            )}
          </Card>

          {summary && (
            <Card>
              <h2 className="display-sm text-ink">At a glance</h2>
              <dl className="mt-3 space-y-2 text-sm">
                <div className="flex justify-between">
                  <dt className="text-muted">Active bookings</dt>
                  <dd className="font-semibold tabular-nums">
                    {summary.total_bookings}
                  </dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-muted">Cancelled</dt>
                  <dd className="font-semibold tabular-nums">
                    {summary.cancelled_bookings}
                  </dd>
                </div>
                <div className="flex justify-between border-t border-hairline pt-2">
                  <dt className="text-muted">Revenue</dt>
                  <dd className="font-semibold tabular-nums">
                    {formatPrice(summary.revenue_cents)}
                  </dd>
                </div>
              </dl>
            </Card>
          )}
        </div>
      </div>

      <section className="space-y-3">
        <h2 className="display-sm text-ink">Bookings</h2>
        {summaryError && <Alert tone="danger">{summaryError}</Alert>}
        {!summary && !summaryError && <Spinner label="Loading bookings" />}

        {summary && summary.bookings.length === 0 && (
          <Card>
            <p className="text-sm text-muted">
              No bookings yet for this event.
            </p>
          </Card>
        )}

        {summary && summary.bookings.length > 0 && (
          <div className="overflow-x-auto rounded-md border border-hairline bg-canvas">
            <table className="w-full min-w-[46rem] text-sm">
              <thead>
                <tr className="border-b border-hairline text-left text-xs uppercase tracking-wide text-muted">
                  <th className="px-4 py-3 font-medium">Reference</th>
                  <th className="px-4 py-3 font-medium">Booker</th>
                  <th className="px-4 py-3 font-medium">Seats</th>
                  <th className="px-4 py-3 text-right font-medium">Amount</th>
                  <th className="px-4 py-3 font-medium">Booked at</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {summary.bookings.map((booking) => (
                  <tr
                    key={booking.id}
                    className={`border-b border-hairline last:border-0 ${
                      booking.status === "CANCELLED" ? "opacity-60" : ""
                    }`}
                  >
                    <td className="px-4 py-3">
                      <Link
                        href={`/bookings/${booking.reference}`}
                        className="font-mono text-xs text-primary underline"
                      >
                        {booking.reference}
                      </Link>
                    </td>
                    <td className="px-4 py-3">
                      <div className="font-medium">{booking.booker_name}</div>
                      <div className="text-xs text-muted">{booking.booker_email}</div>
                    </td>
                    <td className="px-4 py-3">
                      <span className="font-medium">
                        {booking.seat_labels.join(", ")}
                      </span>
                      <span className="ml-2 text-xs text-muted">
                        ({booking.seat_count})
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums">
                      {formatPrice(booking.total_amount_cents)}
                    </td>
                    <td className="px-4 py-3 text-xs text-muted">
                      {formatTimestamp(booking.created_at)}
                    </td>
                    <td className="px-4 py-3">
                      <StatusPill status={booking.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
