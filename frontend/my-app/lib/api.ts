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
export type UserRole = "USER" | "ADMIN";

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface AuthSession {
  user: User;
  tokens: TokenPair;
}

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
  event_date: string | null;
  venue: string | null;
  user_id: number | null;
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
  user_id: number | null;
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

// --- Token storage --------------------------------------------------------
//
// Tokens live in localStorage. The honest trade-off: this is readable by any
// script on the page, so an XSS bug leaks the session. httpOnly cookies would
// not be, but the API is a separate origin, which turns cookies into a
// SameSite=None + CSRF-token exercise. Given a short-lived access token and a
// rotating, revocable refresh token, localStorage is the reasonable choice at
// this scale -- see the README for what would change in production.

const ACCESS_KEY = "seatbook.access_token";
const REFRESH_KEY = "seatbook.refresh_token";

type AuthListener = () => void;
const listeners = new Set<AuthListener>();

export function onAuthChange(listener: AuthListener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function notifyAuthChange() {
  listeners.forEach((listener) => listener());
}

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(ACCESS_KEY);
}

function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(REFRESH_KEY);
}

export function storeTokens(tokens: TokenPair) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(ACCESS_KEY, tokens.access_token);
  window.localStorage.setItem(REFRESH_KEY, tokens.refresh_token);
  notifyAuthChange();
}

export function clearTokens() {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(ACCESS_KEY);
  window.localStorage.removeItem(REFRESH_KEY);
  notifyAuthChange();
}

/**
 * Refresh, de-duplicated.
 *
 * Several requests can 401 at once when an access token expires. Without this
 * shared promise each one would refresh separately, and because the backend
 * rotates refresh tokens, the second rotation would look like a replay and log
 * the user out of everything.
 */
let refreshInFlight: Promise<boolean> | null = null;

async function refreshAccessToken(): Promise<boolean> {
  if (refreshInFlight) return refreshInFlight;

  refreshInFlight = (async () => {
    const refresh_token = getRefreshToken();
    if (!refresh_token) return false;
    try {
      const response = await fetch(`${API_BASE_URL}/api/auth/refresh`, {
        method: "POST",
        cache: "no-store",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token }),
      });
      if (!response.ok) {
        clearTokens();
        return false;
      }
      const session = (await response.json()) as AuthSession;
      storeTokens(session.tokens);
      return true;
    } catch {
      return false;
    } finally {
      refreshInFlight = null;
    }
  })();

  return refreshInFlight;
}

interface RequestOptions extends RequestInit {
  /** Send the bearer token. Defaults to true; false for login/register. */
  auth?: boolean;
  /** Internal: stops a refreshed retry from looping. */
  _retried?: boolean;
}

async function request<T>(path: string, init: RequestOptions = {}): Promise<T> {
  const { auth = true, _retried = false, ...rest } = init;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((rest.headers as Record<string, string>) ?? {}),
  };

  const token = auth ? getAccessToken() : null;
  if (token) headers.Authorization = `Bearer ${token}`;

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...rest,
      // Always hit the network: a cached seat map is a wrong seat map.
      cache: "no-store",
      headers,
    });
  } catch {
    throw new ApiError(
      `Could not reach the API at ${API_BASE_URL}. Is the backend running?`,
      0,
      "network_error",
    );
  }

  // An expired access token: refresh once, then replay the original request.
  if (response.status === 401 && auth && token && !_retried) {
    if (await refreshAccessToken()) {
      return request<T>(path, { ...init, _retried: true });
    }
    clearTokens();
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

// --- Auth -----------------------------------------------------------------

export const registerAccount = (input: {
  email: string;
  password: string;
  full_name: string;
}) =>
  request<AuthSession>("/api/auth/register", {
    method: "POST",
    body: JSON.stringify(input),
    auth: false,
  });

export const login = (input: { email: string; password: string }) =>
  request<AuthSession>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify(input),
    auth: false,
  });

export const getMe = () => request<User>("/api/auth/me");

export const getMyBookings = () => request<Booking[]>("/api/auth/me/bookings");

/** Revoke the refresh token server-side, then drop both tokens locally. */
export async function logout(): Promise<void> {
  const refresh_token =
    typeof window === "undefined"
      ? null
      : window.localStorage.getItem("seatbook.refresh_token");
  try {
    if (refresh_token) {
      await request<void>("/api/auth/logout", {
        method: "POST",
        body: JSON.stringify({ refresh_token }),
        auth: false,
      });
    }
  } catch {
    // A failed revoke must not strand the user in a signed-in-looking UI.
  } finally {
    clearTokens();
  }
}

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
