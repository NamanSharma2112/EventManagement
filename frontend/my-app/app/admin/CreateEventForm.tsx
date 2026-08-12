"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Alert, Button, Card, Field, inputClass } from "@/components/ui";
import { ApiError, createEvent, type SectionInput } from "@/lib/api";

interface TierDraft {
  name: string;
  price: string;
  rows: string;
}

const BLANK_TIER: TierDraft = { name: "", price: "0", rows: "1" };

export function CreateEventForm({ onCreated }: { onCreated: () => void }) {
  const router = useRouter();

  const [name, setName] = useState("");
  const [venue, setVenue] = useState("");
  const [description, setDescription] = useState("");
  const [date, setDate] = useState("");
  const [rows, setRows] = useState("8");
  const [columns, setColumns] = useState("10");
  const [defaultPrice, setDefaultPrice] = useState("0");
  const [blockedSeats, setBlockedSeats] = useState("");

  const [useTiers, setUseTiers] = useState(false);
  const [tiers, setTiers] = useState<TierDraft[]>([
    { name: "Gold", price: "4500", rows: "2" },
    { name: "Silver", price: "2500", rows: "6" },
  ]);

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<{ id: number; name: string } | null>(null);

  const rowCount = Number(rows) || 0;
  const tierRowTotal = tiers.reduce((sum, tier) => sum + (Number(tier.rows) || 0), 0);
  const tiersCoverLayout = !useTiers || tierRowTotal === rowCount;
  const seatTotal = rowCount * (Number(columns) || 0);

  function updateTier(index: number, patch: Partial<TierDraft>) {
    setTiers((current) =>
      current.map((tier, i) => (i === index ? { ...tier, ...patch } : tier)),
    );
  }

  async function submit(formEvent: React.FormEvent) {
    formEvent.preventDefault();
    setSubmitting(true);
    setError(null);
    setCreated(null);

    // Prices are entered in whole currency units; the API stores cents.
    const sections: SectionInput[] | null = useTiers
      ? tiers.map((tier) => ({
          name: tier.name.trim(),
          price_cents: Math.round((Number(tier.price) || 0) * 100),
          row_count: Number(tier.rows) || 0,
        }))
      : null;

    try {
      const event = await createEvent({
        name: name.trim(),
        event_date: date,
        venue: venue.trim() || null,
        description: description.trim() || null,
        rows: Number(rows),
        columns: Number(columns),
        sections,
        default_price_cents: useTiers
          ? 0
          : Math.round((Number(defaultPrice) || 0) * 100),
        blocked_seats: blockedSeats
          .split(/[,\s]+/)
          .map((label) => label.trim().toUpperCase())
          .filter(Boolean),
      });
      setCreated({ id: event.id, name: event.name });
      setName("");
      setVenue("");
      setDescription("");
      setBlockedSeats("");
      onCreated();
      router.refresh();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "The event could not be created.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card>
      <form onSubmit={submit} className="space-y-5">
        {created && (
          <Alert tone="success" title="Event created">
            <a href={`/admin/events/${created.id}`} className="underline">
              Open the dashboard for {created.name}
            </a>
          </Alert>
        )}
        {error && <Alert tone="danger">{error}</Alert>}

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Event name">
            <input
              className={inputClass}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Coldplay: Music of the Spheres"
              required
              maxLength={200}
            />
          </Field>
          <Field label="Date and time">
            <input
              className={inputClass}
              type="datetime-local"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              required
            />
          </Field>
          <Field label="Venue" hint="optional">
            <input
              className={inputClass}
              value={venue}
              onChange={(e) => setVenue(e.target.value)}
              placeholder="DY Patil Stadium, Mumbai"
              maxLength={200}
            />
          </Field>
          <Field label="Description" hint="optional">
            <input
              className={inputClass}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="World tour finale"
              maxLength={2000}
            />
          </Field>
        </div>

        <fieldset className="space-y-4 rounded-lg border border-line p-4">
          <legend className="px-1 text-sm font-medium">Seat layout</legend>

          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Rows" hint="A, B, C ...">
              <input
                className={inputClass}
                type="number"
                min={1}
                max={50}
                value={rows}
                onChange={(e) => setRows(e.target.value)}
                required
              />
            </Field>
            <Field label="Seats per row">
              <input
                className={inputClass}
                type="number"
                min={1}
                max={60}
                value={columns}
                onChange={(e) => setColumns(e.target.value)}
                required
              />
            </Field>
            <div className="flex items-end">
              <p className="text-sm text-muted">
                <span className="font-semibold tabular-nums text-foreground">
                  {seatTotal}
                </span>{" "}
                seats will be created
              </p>
            </div>
          </div>

          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={useTiers}
              onChange={(e) => setUseTiers(e.target.checked)}
              className="h-4 w-4 accent-[var(--accent)]"
            />
            Split the rows into priced sections
          </label>

          {useTiers ? (
            <div className="space-y-3">
              {tiers.map((tier, index) => (
                <div key={index} className="grid gap-2 sm:grid-cols-[1fr_1fr_1fr_auto]">
                  <input
                    className={inputClass}
                    value={tier.name}
                    onChange={(e) => updateTier(index, { name: e.target.value })}
                    placeholder="Gold"
                    aria-label={`Section ${index + 1} name`}
                    required
                  />
                  <input
                    className={inputClass}
                    type="number"
                    min={0}
                    step="0.01"
                    value={tier.price}
                    onChange={(e) => updateTier(index, { price: e.target.value })}
                    placeholder="Price"
                    aria-label={`Section ${index + 1} price`}
                    required
                  />
                  <input
                    className={inputClass}
                    type="number"
                    min={1}
                    value={tier.rows}
                    onChange={(e) => updateTier(index, { rows: e.target.value })}
                    placeholder="Rows"
                    aria-label={`Section ${index + 1} row count`}
                    required
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() =>
                      setTiers((current) => current.filter((_, i) => i !== index))
                    }
                    disabled={tiers.length === 1}
                    aria-label={`Remove section ${index + 1}`}
                  >
                    Remove
                  </Button>
                </div>
              ))}

              <div className="flex flex-wrap items-center justify-between gap-3">
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => setTiers((current) => [...current, { ...BLANK_TIER }])}
                >
                  Add section
                </Button>
                <p
                  className={`text-sm ${tiersCoverLayout ? "text-muted" : "text-danger"}`}
                >
                  Sections cover{" "}
                  <span className="font-semibold tabular-nums">{tierRowTotal}</span> of{" "}
                  <span className="font-semibold tabular-nums">{rowCount}</span> rows
                  {!tiersCoverLayout && " - these must match"}
                </p>
              </div>
            </div>
          ) : (
            <Field label="Ticket price" hint="applies to every seat">
              <input
                className={inputClass}
                type="number"
                min={0}
                step="0.01"
                value={defaultPrice}
                onChange={(e) => setDefaultPrice(e.target.value)}
              />
            </Field>
          )}

          <Field
            label="Block seats at creation"
            hint="optional, e.g. A1 A2 H12 - VIP holds or out-of-service seats"
          >
            <input
              className={inputClass}
              value={blockedSeats}
              onChange={(e) => setBlockedSeats(e.target.value)}
              placeholder="A1, A2, H12"
            />
          </Field>
        </fieldset>

        <Button type="submit" disabled={submitting || !tiersCoverLayout}>
          {submitting ? "Creating..." : "Create event"}
        </Button>
      </form>
    </Card>
  );
}
