# Event Seat Booking

A full-stack seat booking app. An admin lays out an event's seating and blocks
seats; users pick seats from a live map and book them. Two people who click the
same seat at the same moment cannot both get it — and that guarantee lives in
the database, not in Python.

**Next.js 16 · FastAPI · MySQL 8**

```
frontend/my-app   Next.js (App Router, Tailwind v4) — seat map, booking flow, admin
backend           FastAPI + SQLAlchemy — REST API, MySQL schema, tests
docker-compose.yml
```

| | |
|---|---|
| Frontend | http://localhost:3000 |
| API docs (Swagger) | http://localhost:8000/docs |
| Admin | http://localhost:3000/admin |

---

## Table of contents

1. [Quick start](#quick-start)
2. [Concurrency — how double-booking is prevented](#concurrency--how-double-booking-is-prevented)
3. [Demonstrating the race](#demonstrating-the-race)
4. [Schema design](#schema-design)
5. [API](#api)
6. [Frontend](#frontend)
7. [Tests](#tests)
8. [Deployment](#deployment)
9. [Trade-offs and known limitations](#trade-offs-and-known-limitations)

---

## Quick start

### With Docker (one command)

```bash
docker compose up --build
```

That starts MySQL, applies `backend/schema.sql`, runs the API on `:8000` and the
frontend on `:3000`. Open http://localhost:3000/admin and create an event, or
seed demo data:

```bash
docker compose exec api python scripts/seed.py
```

### Without Docker

You need Python 3.11+, Node 20.9+ and a MySQL 8 server.

**1. Database**

```bash
mysql -u root -p < backend/schema.sql

mysql -u root -p -e "
  CREATE DATABASE IF NOT EXISTS seatbooking_test
    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
  CREATE USER IF NOT EXISTS 'seatuser'@'%' IDENTIFIED BY 'seatpass';
  GRANT ALL PRIVILEGES ON seatbooking.*      TO 'seatuser'@'%';
  GRANT ALL PRIVILEGES ON seatbooking_test.* TO 'seatuser'@'%';
  FLUSH PRIVILEGES;"
```

**2. Backend**

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                 # edit if your MySQL differs

python scripts/seed.py                               # optional demo data
uvicorn app.main:app --reload --port 8000
```

`AUTO_CREATE_TABLES=true` (the default) means the API creates the tables itself
on startup, so step 1's `schema.sql` is optional for local work. In production,
run `schema.sql` and set it to `false`.

**3. Frontend**

```bash
cd frontend/my-app
npm install
cp .env.example .env.local                           # NEXT_PUBLIC_API_BASE_URL
npm run dev
```

---

## Concurrency — how double-booking is prevented

The requirement is that if two booking requests for the same seat arrive
together, exactly one succeeds and the other is rejected — enforced by the
database, not by an application-level "is this seat free?" check.

There are **three** layers here. Only the third one is the guarantee; the first
two exist to make the common path fast and the error messages useful.

### Layer 1 — row locks, taken in a fixed order

`app/services/bookings.py` opens a transaction and locks the requested `seats`
rows before it looks at anything else:

```python
seats = db.execute(
    select(Seat)
    .where(Seat.event_id == event.id, Seat.id.in_(payload.seat_ids))
    .order_by(Seat.id.asc())     # deterministic lock order
    .with_for_update()           # SELECT ... FOR UPDATE
).scalars().all()
```

`SELECT ... FOR UPDATE` takes an exclusive row lock held until commit or
rollback. A second transaction asking for the same seat **blocks here** until
the first one finishes — that is what serialises the racers.

The `ORDER BY id` matters. Without it, one request booking `{5, 9}` and another
booking `{9, 5}` could each hold one lock and wait for the other's: a deadlock.
Seat ids are always locked ascending, so the second request always waits for the
first rather than tangling with it. (`BookingCreate` also sorts and de-duplicates
`seat_ids` on the way in.)

### Layer 2 — re-check availability under the lock

Once the lock is granted, the transaction re-reads whether any of those seats
already has an active claim, and whether the admin has blocked them. If so it
raises before writing anything, and the API answers **409 Conflict** naming the
seats:

```json
{
  "detail": "Seats no longer available: A4. No seats were booked.",
  "code": "seat_unavailable",
  "conflicting_seats": [
    { "seat_id": 4, "label": "A4", "reason": "Seat has already been booked." }
  ]
}
```

For this re-read to be correct it has to see writes committed *while we were
waiting*. The engine therefore runs at **READ COMMITTED** instead of MySQL's
default REPEATABLE READ (`app/database.py`), for two reasons:

- Under REPEATABLE READ, plain `SELECT`s read the snapshot from the start of
  the transaction, so a booker that just waited on a lock could still read a
  stale "seat is free". READ COMMITTED takes a fresh snapshot per statement.
- REPEATABLE READ also adds *gap locks* around scanned index ranges. Two
  bookings for neighbouring seats can then deadlock on each other's gaps. READ
  COMMITTED locks only the rows actually matched.

### Layer 3 — the unique index (this is the guarantee)

Seat ownership lives in `booking_seats`, one row per seat per booking. Two
generated columns mirror `event_id`/`seat_id` only while the row is active:

```sql
is_active       TINYINT(1) NOT NULL DEFAULT 1,

active_event_id BIGINT GENERATED ALWAYS AS
  (CASE WHEN is_active = 1 THEN event_id ELSE NULL END) VIRTUAL,
active_seat_id  BIGINT GENERATED ALWAYS AS
  (CASE WHEN is_active = 1 THEN seat_id  ELSE NULL END) VIRTUAL,

UNIQUE KEY uq_booking_seats_active (active_event_id, active_seat_id)
```

MySQL's unique indexes ignore rows with a NULL key part, which gives exactly the
semantics needed:

- **At most one active row per (event, seat)** → a seat cannot be double-booked.
- **Cancelled rows fall out of the index** (`is_active = 0` → both columns NULL)
  → the seat becomes bookable again.
- **Cancelled rows are still stored** → the booking history survives for the
  admin dashboard.

This holds no matter what the application does. If layers 1 and 2 were deleted
tomorrow, a concurrent duplicate would still fail with `ER_DUP_ENTRY (1062)`;
`create_booking` catches that `IntegrityError` and returns the same 409. There
is a test that proves it by writing straight to `booking_seats` and bypassing
the service layer entirely (`test_unique_index_rejects_a_duplicate_written_behind_the_services_back`).

> The columns are `VIRTUAL`, not `STORED`, because MySQL forbids `ON DELETE
> CASCADE` on a column that a *stored* generated column derives from, and the
> cascades from `events`/`seats` are worth keeping. A unique index on a virtual
> column is materialised in the index and enforced identically.

### All-or-nothing multi-seat bookings

Everything above runs inside **one transaction**. If a user selects three seats
and the third has just gone, the conflict is raised before commit and the
rollback takes the first two with it. No partial booking is ever visible, and
the response says so explicitly. `test_multi_seat_booking_is_all_or_nothing`
asserts the untaken seats are still `AVAILABLE` afterwards and that no booking
row was created.

---

## Demonstrating the race

**Automated, over HTTP** — this is the one to run in an interview:

```bash
cd backend
python scripts/concurrency_demo.py --racers 12
```

All 12 requests are held at a barrier and released at the same instant against a
freshly created single-seat event:

```
12 requests, all launched at once, all asking for seat(s) A1 of event 3.

  racer   0  409 CONFLICT  Seats no longer available: A1. No seats were booked.
  racer   1  409 CONFLICT  Seats no longer available: A1. No seats were booked.
  ...
  racer   7  201 CREATED   booked A1 (ref BK-ZL26CFPN)
  ...

  results: {'409': 11, '201': 1}
  seats booked in the database afterwards: ['A1']

  PASS -- exactly one request won; every other one got 409.
```

It exits non-zero if more than one request wins, so it also works as a smoke
test. Other modes:

```bash
python scripts/concurrency_demo.py --racers 25     # more racers
python scripts/concurrency_demo.py --seats 3       # every racer wants the same 3 seats
python scripts/concurrency_demo.py --event-id 1    # race seats on an existing event
```

`--seats 3` is the group-booking case: one winner takes all three, and every
loser books nothing at all. For genuinely *overlapping* groups (`{A1,A2,A3}` vs
`{A3,A4,A5}`, sharing one seat) see
`test_overlapping_group_bookings_never_partially_apply`.

**By hand**, two seats in one shell:

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST localhost:8000/api/bookings \
  -H 'Content-Type: application/json' \
  -d '{"event_id":1,"seat_ids":[3],"booker_name":"A","booker_email":"a@x.com"}' &
curl -s -o /dev/null -w "%{http_code}\n" -X POST localhost:8000/api/bookings \
  -H 'Content-Type: application/json' \
  -d '{"event_id":1,"seat_ids":[3],"booker_name":"B","booker_email":"b@x.com"}' &
wait
# 201
# 409
```

**In the UI**: open the same event in two browser windows, select the same seat
in both, and confirm one after the other. The loser gets "Those seats just went"
with the seat named, and the map refreshes to show it as booked.

---

## Schema design

```
events ──┬── sections ──┐
         │              │
         ├── seats ─────┘        (seats.section_id → sections.id)
         │     │
         │     └──────────┐
         └── bookings ────┴── booking_seats
```

**Five tables, in dependency order.** Full DDL with comments:
[`backend/schema.sql`](backend/schema.sql); the ORM models mirror it exactly in
[`backend/app/models.py`](backend/app/models.py).

### Why rows × columns rather than named sections

The brief allows either. This uses **rows × columns as the physical layout, with
named sections layered on top** — which gets both:

- A grid is what a seat actually is. `(row_label, seat_number)` gives every seat
  a stable human address (`A1`, `H12`) that the UI, the admin's block list and
  the booking confirmation can all share, and the seat map renders straight from
  it with no extra layout metadata.
- **Sections** (`Gold`, `Silver`, …) are a separate table that owns the *price*
  and covers a contiguous span of rows. That keeps price normalised — one row
  per tier, not per seat — and gives the price-tier bonus without a second
  layout model.

An event created without explicit tiers gets one auto-generated `General`
section, so `seats.section_id` can stay `NOT NULL` rather than nullable.

### Why seat status is derived, never stored

There is no `seats.status` column. A seat's status is computed:

| Condition | Status |
|---|---|
| an active `booking_seats` row points at it | `BOOKED` |
| otherwise, `seats.is_blocked = 1` | `BLOCKED` |
| otherwise | `AVAILABLE` |

A stored status would be a second source of truth that has to be kept in sync
with the bookings table — exactly the kind of drift that produces a seat marked
free while a booking row still claims it. Deriving it means cancellation is a
single `is_active = 0` update and the seat is free again, with no denormalised
field to forget. The dashboard totals and the seat map use the same derivation
(`_counts_query()` in `services/events.py`), so they cannot disagree.

`is_blocked` lives on `seats` rather than being modelled as a fake booking,
because an admin hold is a property of the seat, not of a booker — it has no
name, no email and no reference.

### Other constraints worth calling out

| Constraint | Why |
|---|---|
| `uq_seats_event_row_number (event_id, row_label, seat_number)` | no two seats in an event share a coordinate |
| `uq_sections_event_name (event_id, name)` | tier names are unique per event, not globally |
| `uq_bookings_reference` | booking references are the public handle; they must be unique |
| `ck_seats_number_positive`, `ck_sections_price_non_negative` | cheap sanity guards in the database |
| `seats.section_id → sections.id ON DELETE RESTRICT` | a tier with seats in it must not vanish |
| `booking_seats.price_cents` | price captured at booking time, so a later tier change cannot rewrite what someone paid |

`booking_seats.event_id` is denormalised (it is reachable via `seats`) so the
unique key can be expressed on the `(event, seat)` pair as one index.

---

## API

Interactive docs at `/docs`; the OpenAPI schema at `/openapi.json`.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/events` | Create an event and generate its seats → `201` |
| `GET` | `/api/events` | List events with seat counts |
| `GET` | `/api/events/{id}` | Event detail |
| `GET` | `/api/events/{id}/seats` | **Seat map** with derived statuses |
| `POST` | `/api/events/{id}/seats/block` | Block/unblock seats (admin) |
| `GET` | `/api/events/{id}/summary` | **Admin dashboard**: totals + every booking |
| `DELETE` | `/api/events/{id}` | Delete an event and everything under it |
| `POST` | `/api/bookings` | **Book seats** → `201`, or `409` on conflict |
| `GET` | `/api/bookings/{reference}` | Look up a booking |
| `POST` | `/api/bookings/{reference}/cancel` | Cancel and release the seats |
| `GET` | `/health` | Liveness + database check |

### Status codes

| Code | When |
|---|---|
| `201` | Event or booking created |
| `200` | Read, block/unblock, cancel |
| `204` | Event deleted |
| `404` | Unknown event, seat, or booking reference |
| `409` | **Seat already booked or blocked**, or booking already cancelled |
| `422` | Invalid payload (bad email, empty seat list, layout over the caps) |

Every 4xx uses one envelope — `detail`, a machine-readable `code`, and for seat
conflicts a `conflicting_seats` array — so the UI can highlight exactly which
seats clashed rather than showing a generic failure.

### Creating an event

```bash
curl -X POST localhost:8000/api/events -H 'Content-Type: application/json' -d '{
  "name": "Coldplay: Music of the Spheres",
  "event_date": "2026-09-18T19:30:00",
  "venue": "DY Patil Stadium, Mumbai",
  "rows": 8,
  "columns": 12,
  "sections": [
    {"name": "Gold",   "price_cents": 450000, "row_count": 2},
    {"name": "Silver", "price_cents": 250000, "row_count": 3},
    {"name": "Bronze", "price_cents": 120000, "row_count": 3}
  ],
  "blocked_seats": ["A1", "A2", "A11", "A12"]
}'
```

Section `row_count`s must add up to `rows` — a mismatch is a `422` with the
numbers in the message. Layout size is capped by `MAX_*` settings (default 2000
seats per event, 10 seats per booking) so a typo cannot ask for a million rows.

---

## Frontend

| Route | What it does |
|---|---|
| `/` | Event list with live seat counts |
| `/events/[id]` | Seat map, multi-seat selection, booking form |
| `/bookings` | Look up a booking by reference |
| `/bookings/[reference]` | Confirmation; cancel a booking |
| `/admin` | Event list + create-event form |
| `/admin/events/[id]` | Dashboard: totals, revenue, seat blocking, booking table |

**Design system.** The UI follows
[`frontend/my-app/DESIGN.md`](frontend/my-app/DESIGN.md) — an Airbnb-derived
system: white canvas, near-black ink, and a single voltage of Rausch (`#ff385c`)
reserved for primary CTAs and the selected-seat state. Soft shape language
throughout (8px buttons, 14px cards, full-pill badges), one shadow tier used
only on hover-float, and Inter standing in for Airbnb Cereal VF. The tokens live
as CSS custom properties in `app/globals.css` and are exposed to Tailwind via
`@theme inline`, so nothing hard-codes a hex. DESIGN.md notes Airbnb has no dark
mode on the public web; the dark palette here is this project's own extension,
derived from the same tokens.

**Seat states** are distinguished by colour *and* shape, so the map stays
readable in greyscale or with a colour vision deficiency: available is outlined,
selected is Rausch-filled and lifted, booked is solid grey, blocked is hatched.
Every seat is a real `<button>` with an `aria-label` spelling out its row,
section, price and status.

**Staying current.** `usePolledResource` refetches every 5s while the tab is
visible, and immediately on window focus — the brief's "polling or
refetch-on-focus is sufficient". Polling pauses on hidden tabs and never flips
the loading state back on, so the map does not flash. A failed poll leaves the
existing map on screen rather than replacing it with an error.

**The selection is derived, not stored.** The component keeps a list of picked
seat *ids* and derives the actual selection from the current seat map on every
render. A seat that someone else books between polls simply stops counting as
selected, and the user gets a "seats taken while you were choosing" notice — the
UI has no way to disagree with the server about what is available.

**States handled**: loading (spinner + seat skeleton), empty (no events yet),
network failure (the API being down is reported as such), booked/blocked seats
(not selectable), selected, submitting, success (with the reference linked), and
409 conflict (the clashing seats are named and flashed on the map).

**Responsiveness**: single column below `lg`, with the seat map scrolling inside
its own container so the page itself never scrolls sideways. Verified in
Chromium at 320, 390, 768, 1280 and 1600 px — zero horizontal page overflow at
every one — in both light and dark.

---

## Tests

```bash
cd backend
pip install -r requirements-dev.txt
pytest                    # 32 tests
pytest tests/test_concurrency.py -v
```

Tests run against a **real MySQL** database (`seatbooking_test`), which is the
point: the guarantees under test are InnoDB row locks and a MySQL unique index,
so an in-memory stand-in would prove nothing. Set `MYSQL_DATABASE` to change the
target.

The concurrency suite uses real threads on real connections, released together
by a `threading.Barrier`:

| Test | What it proves |
|---|---|
| `test_simultaneous_bookings_for_one_seat_leave_exactly_one_winner` | 2 and 10 racers on one seat → exactly 1 × `201`, the rest `409`; one active row in the database |
| `test_overlapping_group_bookings_never_partially_apply` | `{A1,A2,A3}` vs `{A3,A4,A5}` → one wins entirely, the loser books nothing |
| `test_stampede_over_a_small_seat_pool_never_double_books` | 40 requests over 5 seats → no seat claimed twice, seats held = winners × 2 |
| `test_freed_seat_can_be_won_by_exactly_one_racer` | after a cancellation, 6 racers contest the freed seat → still one winner |
| `test_unique_index_rejects_a_duplicate_written_behind_the_services_back` | a raw INSERT bypassing the service layer is still rejected by the index |
| `test_cancelled_rows_leave_the_unique_index` | two claims on one seat coexist as history; only one is active |
| `test_booking_transaction_takes_a_row_lock_on_the_seat` | a second connection using `FOR UPDATE NOWAIT` is refused while the lock is held |

Plus `test_events.py` (layout generation, row labels past Z, tier validation,
blocking, count consistency across all three endpoints) and `test_bookings.py`
(happy path, 409s, atomicity, validation, cancellation).

Frontend checks:

```bash
cd frontend/my-app
npm run lint          # ESLint, including the React Compiler rules
npx tsc --noEmit      # after `npx next typegen`
npm run build
```

---

## Deployment

The two halves deploy independently; the frontend only needs
`NEXT_PUBLIC_API_BASE_URL` pointing at the API.

**Frontend → Vercel.** Set the project root to `frontend/my-app` and add
`NEXT_PUBLIC_API_BASE_URL` as an environment variable. It is inlined into the
client bundle at build time, so changing it requires a redeploy.

**Backend → any container host** (Railway, Render, Fly.io, an EC2 box). Build
`backend/Dockerfile` and set:

| Variable | Notes |
|---|---|
| `DATABASE_URL` | or the `MYSQL_*` parts individually |
| `CORS_ORIGINS` | must include the deployed frontend origin, comma separated |
| `AUTO_CREATE_TABLES` | `false` in production; run `schema.sql` once instead |
| `TZ` | `UTC`, and run MySQL with `--default-time-zone=+00:00` |

**Database → any managed MySQL 8** (PlanetScale, RDS, Railway). Apply
`backend/schema.sql` once.

Two things to get right:

- **CORS.** The seat map is fetched from the browser, so the API must list the
  frontend's exact origin in `CORS_ORIGINS` — scheme and port included.
- **Timestamps.** `created_at` uses MySQL's `NOW()` and `cancelled_at` uses the
  API process's clock. Run both in UTC so they agree.

---

## Trade-offs and known limitations

**No seat hold / reservation window.** Seats are taken at the moment of
confirmation, not when they are selected. Someone can lose a seat they had
highlighted while filling in the form — the UI handles that gracefully, but a
real ticketing system would put a short TTL hold on selection. The schema is
ready for it: a `holds` table with an expiry, or a `held_until` column on
`booking_seats` with the unique index widened to cover held rows.

**No authentication anywhere.** The brief says admin needs none, and `/admin` is
open by design. It should not be, in production — the block and delete endpoints
would let anyone sabotage an event.

**Polling, not push.** A 5-second poll per open seat map is fine for a demo and
matches the brief. At real concurrency it is wasteful; server-sent events or a
WebSocket per event room would be the next step.

**READ COMMITTED is a deliberate choice, not a default.** It makes the
availability re-check see fresh data and removes gap-lock deadlocks. Anything
added later that relies on repeatable reads within a transaction would need to
account for it.

**Bookings are never expired or garbage collected.** Cancelled `booking_seats`
rows accumulate as history. Fine at this scale; a real system would partition or
archive.

**Money is `INT` cents.** Correct and exact for these amounts, but it caps a
single line at ~21 million rupees and assumes one currency. A multi-currency
system would need a currency column and a wider type.

**Row locking serialises per seat, not per event.** Two bookings for different
seats never block each other, which is what you want — but a single very popular
seat is a serialisation point by construction. That is inherent to the
guarantee, not a defect.

**No rate limiting.** The booking endpoint will happily accept as many requests
as it is given; the concurrency demo is proof of that.
