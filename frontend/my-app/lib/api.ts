/**
 * Typed client for the FastAPI backend.
 *
 * Everything the UI does goes through here, so there is one place that knows
 * the base URL and one place that turns the API's error envelope into a real
 * Error the components can render.
 */

export const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000"
).replace(/\/$/, "");

export type SeatStatus = "AVAILABLE" | "BOOKED" | "BLOCKED";
export type BookingStatus = "CONFIRMED" | "CANCELLED";

export interface Section {
  id: number;
  name: string;
  price_cents: number;
  display_order: number;
}

export interface EventDetail {
  id: number;
  name: string;
  description: string | null;
  venue: string | null;
  event_date: string;
  row_count: number;
  column_count: number;
  created_at: string;
  sections: Section[];
}

export interface EventSummary {
  id: number;
  name: string;
  description: string | null;
  venue: string | null;
  event_date: string;
  row_count: number;
  column_count: number;
  created_at: string;
  total_seats: number;
  booked_seats: number;
  blocked_seats: number;
  available_seats: number;
}

export interface Seat {
  id: number;
  label: string;
  row_label: string;
  row_index: number;
  seat_number: number;
  section_id: number;
  section_name: string;
  price_cents: number;
  status: SeatStatus;
  blocked_reason: string | null;
}

export interface SeatRow {
  row_label: string;
  row_index: number;
  seats: Seat[];
}

export interface SeatMap {
  event: EventDetail;
  rows: SeatRow[];
  total_seats: number;
  booked_seats: number;
  blocked_seats: number;
  available_seats: number;
  generated_at: string;
}

export interface BookedSeat {
  seat_id: number;
  label: string;
  section_name: string;
  price_cents: number;
}

export interface Booking {
  id: number;
  reference: string;
  event_id: number;
  event_name: string;
  booker_name: string;
  booker_email: string;
  status: BookingStatus;
  total_amount_cents: number;
  created_at: string;
  cancelled_at: string | null;
  seats: BookedSeat[];
}

export interface AdminBookingRow {
  id: number;
  reference: string;
  booker_name: string;
  booker_email: string;
  status: BookingStatus;
  seat_labels: string[];
  seat_count: number;
  total_amount_cents: number;
  created_at: string;
  cancelled_at: string | null;
}

export interface AdminSummary {
  event: EventDetail;
  total_seats: number;
  booked_seats: number;
  blocked_seats: number;
  available_seats: number;
  total_bookings: number;
  cancelled_bookings: number;
  revenue_cents: number;
  bookings: AdminBookingRow[];
}

export interface ConflictSeat {
  seat_id: number;
  label: string;
  reason: string;
}

/** An error carrying the backend's status code and, for 409s, the clashing seats. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly conflictingSeats: ConflictSeat[];

  constructor(
    message: string,
    status: number,
    code: string,
    conflictingSeats: ConflictSeat[] = [],
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.conflictingSeats = conflictingSeats;
  }

  /** True when a seat was taken between loading the map and pressing confirm. */
  get isConflict() {
    return this.status === 409;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      // Always hit the network: a cached seat map is a wrong seat map.
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers ?? {}),
      },
    });
  } catch {
    throw new ApiError(
      `Could not reach the API at ${API_BASE_URL}. Is the backend running?`,
      0,
      "network_error",
    );
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const body = await response.json().catch(() => null);

  if (!response.ok) {
    throw new ApiError(
      body?.detail ?? `Request failed with status ${response.status}`,
      response.status,
      body?.code ?? "error",
      body?.conflicting_seats ?? [],
    );
  }

  return body as T;
}

// --- Events ---------------------------------------------------------------

export interface SectionInput {
  name: string;
  price_cents: number;
  row_count: number;
}

export interface CreateEventInput {
  name: string;
  event_date: string;
  description?: string | null;
  venue?: string | null;
  rows: number;
  columns: number;
  sections?: SectionInput[] | null;
  default_price_cents?: number;
  blocked_seats?: string[];
}

export const listEvents = () => request<EventSummary[]>("/api/events");

export const getEvent = (eventId: number) =>
  request<EventDetail>(`/api/events/${eventId}`);

export const getSeatMap = (eventId: number) =>
  request<SeatMap>(`/api/events/${eventId}/seats`);

export const createEvent = (input: CreateEventInput) =>
  request<EventDetail>("/api/events", {
    method: "POST",
    body: JSON.stringify(input),
  });

export const deleteEvent = (eventId: number) =>
  request<void>(`/api/events/${eventId}`, { method: "DELETE" });

export const getAdminSummary = (eventId: number) =>
  request<AdminSummary>(`/api/events/${eventId}/summary`);

export interface BlockSeatsInput {
  seat_ids?: number[];
  seat_labels?: string[];
  blocked: boolean;
  reason?: string | null;
}

export const setSeatsBlocked = (eventId: number, input: BlockSeatsInput) =>
  request<{ updated_seat_ids: number[]; blocked: boolean; skipped_booked_seat_ids: number[] }>(
    `/api/events/${eventId}/seats/block`,
    { method: "POST", body: JSON.stringify(input) },
  );

// --- Bookings -------------------------------------------------------------

export interface CreateBookingInput {
  event_id: number;
  seat_ids: number[];
  booker_name: string;
  booker_email: string;
}

export const createBooking = (input: CreateBookingInput) =>
  request<Booking>("/api/bookings", {
    method: "POST",
    body: JSON.stringify(input),
  });

export const getBooking = (reference: string) =>
  request<Booking>(`/api/bookings/${encodeURIComponent(reference)}`);

export const cancelBooking = (reference: string) =>
  request<Booking>(`/api/bookings/${encodeURIComponent(reference)}/cancel`, {
    method: "POST",
  });

// --- Formatting -----------------------------------------------------------

export function formatPrice(cents: number): string {
  if (cents === 0) return "Free";
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(cents / 100);
}

export function formatEventDate(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export function formatTimestamp(iso: string): string {
  // Timestamps without an offset are the server's wall clock and are shown as
  // written, which is what JS does for offset-less date-time strings.
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "medium",
  });
}
