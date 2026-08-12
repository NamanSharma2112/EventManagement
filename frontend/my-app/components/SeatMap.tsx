"use client";

import { formatPrice, type Seat, type SeatMap as SeatMapData } from "@/lib/api";

/** Legend and seat share one class table, so the two can never drift apart. */
const STATUS_CLASS: Record<string, string> = {
  AVAILABLE: "seat--available",
  SELECTED: "seat--selected",
  BOOKED: "seat--booked",
  BLOCKED: "seat--blocked",
};

function seatTitle(seat: Seat, selected: boolean): string {
  const price = seat.price_cents > 0 ? ` - ${formatPrice(seat.price_cents)}` : "";
  const where = `${seat.label} (${seat.section_name})${price}`;
  if (seat.status === "BOOKED") return `${where} - already booked`;
  if (seat.status === "BLOCKED")
    return `${where} - unavailable${seat.blocked_reason ? `: ${seat.blocked_reason}` : ""}`;
  return `${where} - ${selected ? "selected, click to remove" : "available"}`;
}

export function SeatLegend({ className = "" }: { className?: string }) {
  const items = [
    { key: "AVAILABLE", label: "Available" },
    { key: "SELECTED", label: "Selected" },
    { key: "BOOKED", label: "Booked" },
    { key: "BLOCKED", label: "Unavailable" },
  ];
  return (
    <ul className={`flex flex-wrap items-center gap-x-5 gap-y-2 ${className}`}>
      {items.map(({ key, label }) => (
        <li key={key} className="flex items-center gap-2 text-xs text-muted">
          <span
            aria-hidden
            className={`seat ${STATUS_CLASS[key]}`}
            style={{ width: "1.1rem", minWidth: "1.1rem", transform: "none" }}
          />
          {label}
        </li>
      ))}
    </ul>
  );
}

/** Bookers may only pick free seats; admins may also pick blocked ones to release. */
const bookableOnly = (seat: Seat) => seat.status === "AVAILABLE";

export function SeatMap({
  seatMap,
  selectedIds,
  conflictIds = [],
  onToggleSeat,
  disabled = false,
  isSelectable = bookableOnly,
}: {
  seatMap: SeatMapData;
  selectedIds: Set<number>;
  conflictIds?: number[];
  onToggleSeat: (seat: Seat) => void;
  disabled?: boolean;
  isSelectable?: (seat: Seat) => boolean;
}) {
  const columns = Math.max(
    seatMap.event.column_count,
    ...seatMap.rows.map((row) => row.seats.length),
    1,
  );
  const conflicts = new Set(conflictIds);

  return (
    <div className="w-full">
      <div className="mb-1 text-center text-[0.65rem] font-medium uppercase tracking-[0.2em] text-muted">
        Stage
      </div>
      <div className="stage mb-6" aria-hidden />

      {/* Wide layouts scroll inside this box instead of stretching the page. */}
      <div className="-mx-1 overflow-x-auto px-1 pb-2">
        <div className="mx-auto w-fit min-w-full space-y-1.5">
          {seatMap.rows.map((row) => (
            <div key={row.row_index} className="flex items-center gap-2">
              <span className="w-5 shrink-0 text-right text-[0.7rem] font-semibold text-muted">
                {row.row_label}
              </span>
              {/* justify-center keeps the block of seats centred once the
                  columns hit their max width and stop stretching. */}
              <div
                className="grid flex-1 justify-center gap-1.5"
                style={{
                  gridTemplateColumns: `repeat(${columns}, minmax(1.65rem, 2.25rem))`,
                }}
              >
                {row.seats.map((seat) => {
                  const isSelected = selectedIds.has(seat.id);
                  const visualStatus = isSelected ? "SELECTED" : seat.status;
                  const selectable = isSelectable(seat) && !disabled;

                  return (
                    <button
                      key={seat.id}
                      type="button"
                      disabled={!selectable && !isSelected}
                      aria-pressed={isSelected}
                      aria-label={seatTitle(seat, isSelected)}
                      title={seatTitle(seat, isSelected)}
                      onClick={() => onToggleSeat(seat)}
                      className={`seat ${STATUS_CLASS[visualStatus]} ${
                        conflicts.has(seat.id) ? "seat--conflict" : ""
                      }`}
                      style={selectable ? { cursor: "pointer" } : undefined}
                    >
                      {seat.seat_number}
                    </button>
                  );
                })}
              </div>
              <span className="w-5 shrink-0 text-[0.7rem] font-semibold text-muted">
                {row.row_label}
              </span>
            </div>
          ))}
        </div>
      </div>

      {seatMap.event.sections.length > 1 && (
        <ul className="mt-5 flex flex-wrap gap-x-5 gap-y-1 border-t border-line pt-4 text-xs text-muted">
          {seatMap.event.sections.map((section) => (
            <li key={section.id}>
              <span className="font-medium text-foreground">{section.name}</span>{" "}
              {formatPrice(section.price_cents)}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
