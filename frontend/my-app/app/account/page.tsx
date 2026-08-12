"use client";

import Link from "next/link";
import { useCallback } from "react";

import { useAuth } from "@/components/AuthProvider";
import { RequireAuth } from "@/components/RequireAuth";
import { Alert, Button, Card, Spinner, StatusPill } from "@/components/ui";
import { usePolledResource } from "@/hooks/usePolledResource";
import { formatEventDate, formatPrice, getMyBookings } from "@/lib/api";

export default function AccountPage() {
  return (
    <RequireAuth redirectTo="/account">
      <AccountContent />
    </RequireAuth>
  );
}

function AccountContent() {
  const { user, signOut } = useAuth();
  const fetcher = useCallback(() => getMyBookings(), []);
  const { data: bookings, loading, error } = usePolledResource(fetcher, {
    fallbackMessage: "Could not load your bookings.",
  });

  const active = bookings?.filter((b) => b.status === "CONFIRMED") ?? [];
  const spend = active.reduce((sum, b) => sum + b.total_amount_cents, 0);

  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="display-xl text-ink">Your account</h1>
          <p className="mt-1 text-base text-muted">
            {user?.full_name} &middot; {user?.email}
            {user?.role === "ADMIN" && (
              <span className="ml-2 rounded-full border border-hairline bg-surface-strong px-2.5 py-1 text-[11px] font-semibold text-ink">
                Admin
              </span>
            )}
          </p>
        </div>
        <Button variant="secondary" onClick={signOut}>
          Sign out
        </Button>
      </header>

      {error && <Alert tone="danger">{error}</Alert>}
      {loading && <Spinner label="Loading your bookings" />}

      {bookings && bookings.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-3">
          <Card className="py-4">
            <div className="uppercase-tag text-muted">Active bookings</div>
            <div className="mt-1.5 text-[26px] font-bold tabular-nums">
              {active.length}
            </div>
          </Card>
          <Card className="py-4">
            <div className="uppercase-tag text-muted">Seats held</div>
            <div className="mt-1.5 text-[26px] font-bold tabular-nums">
              {active.reduce((sum, b) => sum + b.seats.length, 0)}
            </div>
          </Card>
          <Card className="py-4">
            <div className="uppercase-tag text-muted">Total spend</div>
            <div className="mt-1.5 text-[26px] font-bold tabular-nums">
              {formatPrice(spend)}
            </div>
          </Card>
        </div>
      )}

      <section className="space-y-3">
        <h2 className="display-sm text-ink">Bookings</h2>

        {bookings?.length === 0 && (
          <Card>
            <p className="text-sm text-muted">
              Nothing booked from this account yet. Bookings you made as a guest
              are not listed here &mdash; look those up with their reference on{" "}
              <Link href="/bookings" className="text-ink underline underline-offset-4">
                the booking page
              </Link>
              .
            </p>
          </Card>
        )}

        {bookings?.map((booking) => (
          <Link
            key={booking.id}
            href={`/bookings/${booking.reference}`}
            className={`flex flex-wrap items-center justify-between gap-4 rounded-md border border-hairline bg-canvas px-5 py-4 transition hover:shadow-tier ${
              booking.status === "CANCELLED" ? "opacity-60" : ""
            }`}
          >
            <div>
              <p className="title-md text-ink">{booking.event_name}</p>
              <p className="mt-0.5 text-sm text-muted">
                {booking.event_date && formatEventDate(booking.event_date)}
                {booking.venue && ` - ${booking.venue}`}
              </p>
              <p className="mt-1 text-sm text-muted">
                {booking.seats.map((s) => s.label).join(", ")}
                <span className="ml-2 font-mono text-[13px]">{booking.reference}</span>
              </p>
            </div>
            <div className="flex items-center gap-4">
              <span className="tabular-nums font-semibold">
                {formatPrice(booking.total_amount_cents)}
              </span>
              <StatusPill status={booking.status} />
            </div>
          </Link>
        ))}
      </section>
    </div>
  );
}
