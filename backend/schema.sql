-- Event Seat Booking -- MySQL 8.0 schema
--
-- The app can create these tables itself on startup (AUTO_CREATE_TABLES=true),
-- but this file is the canonical, reviewable version. It matches what
-- SQLAlchemy emits, byte for byte in behaviour.
--
--   mysql -u root -p < schema.sql
--
-- Tables, in dependency order:
--   users          -> refresh_tokens
--   events         -> sections -> seats
--                  -> bookings -> booking_seats
--
-- Double-booking is prevented by the unique index on booking_seats. Read the
-- comment above that table before changing anything there.

CREATE DATABASE IF NOT EXISTS seatbooking
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE seatbooking;


-- ---------------------------------------------------------------------------
-- users -- accounts. Only the bcrypt hash of a password is ever stored.
--
-- Emails are lower-cased by the application before writing, so this plain
-- unique index makes accounts case-insensitive.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
  id            BIGINT       NOT NULL AUTO_INCREMENT,
  email         VARCHAR(255) NOT NULL,
  password_hash VARCHAR(255) NOT NULL,   -- bcrypt, never a plaintext password
  full_name     VARCHAR(120) NOT NULL,
  role          ENUM('USER','ADMIN') NOT NULL DEFAULT 'USER',
  is_active     TINYINT(1)   NOT NULL DEFAULT 1,
  created_at    DATETIME     NOT NULL DEFAULT (NOW()),
  updated_at    DATETIME     NOT NULL DEFAULT (NOW()) ON UPDATE NOW(),

  PRIMARY KEY (id),
  UNIQUE KEY uq_users_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ---------------------------------------------------------------------------
-- refresh_tokens -- the revocable half of a session
--
-- Only the SHA-256 *hash* of the token is stored, so a database leak cannot be
-- replayed as a login. Tokens rotate on every refresh: the presented one is
-- marked ROTATED and a new one issued.
--
-- revoked_reason is what separates a leak from a logout. Replaying a token that
-- was revoked by ROTATION means someone is using a token the real owner already
-- spent -- so every session for that account is dropped. Replaying one revoked
-- by LOGOUT is just a stale client and must not sign the user out elsewhere.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS refresh_tokens (
  id             BIGINT      NOT NULL AUTO_INCREMENT,
  user_id        BIGINT      NOT NULL,
  token_hash     VARCHAR(64) NOT NULL,   -- sha256 hex of the opaque token
  expires_at     DATETIME    NOT NULL,
  revoked_at     DATETIME    NULL,
  revoked_reason ENUM('ROTATED','LOGOUT','REUSE_DETECTED') NULL,
  created_at     DATETIME    NOT NULL DEFAULT (NOW()),

  PRIMARY KEY (id),
  UNIQUE KEY uq_refresh_tokens_hash (token_hash),
  KEY ix_refresh_tokens_user (user_id),
  CONSTRAINT fk_refresh_tokens_user FOREIGN KEY (user_id)
    REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ---------------------------------------------------------------------------
-- events
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS events (
  id            BIGINT       NOT NULL AUTO_INCREMENT,
  name          VARCHAR(200) NOT NULL,
  description   TEXT         NULL,
  venue         VARCHAR(200) NULL,
  event_date    DATETIME     NOT NULL,

  -- Snapshot of the layout so the seat map can be drawn as a grid without
  -- deriving its dimensions from the seat rows on every request.
  row_count     INT          NOT NULL DEFAULT 0,
  column_count  INT          NOT NULL DEFAULT 0,

  created_at    DATETIME     NOT NULL DEFAULT (NOW()),
  updated_at    DATETIME     NOT NULL DEFAULT (NOW()) ON UPDATE NOW(),

  PRIMARY KEY (id),
  KEY ix_events_event_date (event_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ---------------------------------------------------------------------------
-- sections -- named price tiers inside one event ("Gold", "Silver", ...)
--
-- Every seat belongs to exactly one section. Events created without explicit
-- tiers get a single auto-generated "General" section, which lets seats.section_id
-- stay NOT NULL instead of nullable.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sections (
  id            BIGINT      NOT NULL AUTO_INCREMENT,
  event_id      BIGINT      NOT NULL,
  name          VARCHAR(50) NOT NULL,
  price_cents   INT         NOT NULL DEFAULT 0,
  display_order INT         NOT NULL DEFAULT 0,

  PRIMARY KEY (id),
  UNIQUE KEY uq_sections_event_name (event_id, name),
  CONSTRAINT ck_sections_price_non_negative CHECK (price_cents >= 0),
  CONSTRAINT fk_sections_event FOREIGN KEY (event_id)
    REFERENCES events (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ---------------------------------------------------------------------------
-- seats -- one row per physical seat, addressed as row_label + seat_number (A1)
--
-- is_blocked is the organiser's own hold (VIP, broken seat, sound desk). It is
-- deliberately independent of bookings: a seat can be blocked while nobody has
-- booked it, and a seat's AVAILABLE/BOOKED/BLOCKED status is never stored here
-- -- the API derives it from is_blocked plus booking_seats.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS seats (
  id             BIGINT       NOT NULL AUTO_INCREMENT,
  event_id       BIGINT       NOT NULL,
  section_id     BIGINT       NOT NULL,

  row_label      VARCHAR(4)   NOT NULL,   -- 'A' .. 'Z', 'AA', ...
  row_index      INT          NOT NULL,   -- 0-based, for ordering
  seat_number    INT          NOT NULL,   -- 1-based, within the row

  is_blocked     TINYINT(1)   NOT NULL DEFAULT 0,
  blocked_reason VARCHAR(255) NULL,

  created_at     DATETIME     NOT NULL DEFAULT (NOW()),

  PRIMARY KEY (id),
  UNIQUE KEY uq_seats_event_row_number (event_id, row_label, seat_number),
  KEY ix_seats_event_order (event_id, row_index, seat_number),
  CONSTRAINT ck_seats_number_positive CHECK (seat_number >= 1),
  CONSTRAINT fk_seats_event FOREIGN KEY (event_id)
    REFERENCES events (id) ON DELETE CASCADE,
  -- RESTRICT: a tier that still has seats in it must not vanish.
  CONSTRAINT fk_seats_section FOREIGN KEY (section_id)
    REFERENCES sections (id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ---------------------------------------------------------------------------
-- bookings -- one row per successful booking request (the booker's details)
-- ---------------------------------------------------------------------------
-- user_id is NULL for guest bookings. The brief requires booking without a
-- login, so an account is an optional owner rather than a requirement: a signed
-- in booking gains "my bookings" and an ownership check on cancellation, while
-- a guest booking is reachable only by its reference.
CREATE TABLE IF NOT EXISTS bookings (
  id                 BIGINT       NOT NULL AUTO_INCREMENT,
  event_id           BIGINT       NOT NULL,
  reference          VARCHAR(16)  NOT NULL,   -- 'BK-XXXXXXXX', shown to the booker
  user_id            BIGINT       NULL,       -- NULL = guest booking
  booker_name        VARCHAR(120) NOT NULL,
  booker_email       VARCHAR(255) NOT NULL,
  status             ENUM('CONFIRMED','CANCELLED') NOT NULL DEFAULT 'CONFIRMED',
  total_amount_cents INT          NOT NULL DEFAULT 0,
  created_at         DATETIME     NOT NULL DEFAULT (NOW()),
  cancelled_at       DATETIME     NULL,

  PRIMARY KEY (id),
  UNIQUE KEY uq_bookings_reference (reference),
  KEY ix_bookings_event_created (event_id, created_at),
  KEY ix_bookings_email (booker_email),
  KEY ix_bookings_user_created (user_id, created_at),
  CONSTRAINT fk_bookings_event FOREIGN KEY (event_id)
    REFERENCES events (id) ON DELETE CASCADE,
  -- SET NULL, not CASCADE: deleting an account must not erase the fact that a
  -- seat was sold. The booking survives as a guest booking.
  CONSTRAINT fk_bookings_user FOREIGN KEY (user_id)
    REFERENCES users (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ---------------------------------------------------------------------------
-- booking_seats -- one row per seat inside a booking, and the double-booking guard
--
-- THIS TABLE IS WHERE DOUBLE-BOOKING IS PREVENTED.
--
-- is_active is 1 while the parent booking is CONFIRMED and 0 once cancelled.
-- The two generated columns mirror event_id/seat_id only while the row is
-- active and are NULL otherwise. MySQL's unique indexes ignore rows with a NULL
-- key part, so:
--
--   * at most ONE active row can exist per (event_id, seat_id)  -> no double-booking
--   * cancelled rows fall out of the index                      -> the seat frees up
--   * cancelled rows are still stored                           -> history is kept
--
-- This holds regardless of what the application does. Two concurrent INSERTs
-- for the same seat cannot both commit: the second gets ER_DUP_ENTRY (1062),
-- which the API turns into 409 Conflict.
--
-- The columns are VIRTUAL, not STORED, because MySQL forbids ON DELETE CASCADE
-- on a column that a stored generated column is derived from -- and the
-- cascades from events/seats are worth keeping. A unique index on a virtual
-- column is materialised in the index and enforced identically.
--
-- event_id is denormalised here (it is reachable through seats) purely so the
-- unique key can be stated on the (event, seat) pair as a single index.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS booking_seats (
  id              BIGINT     NOT NULL AUTO_INCREMENT,
  booking_id      BIGINT     NOT NULL,
  seat_id         BIGINT     NOT NULL,
  event_id        BIGINT     NOT NULL,

  -- Price captured at booking time, so later tier changes cannot rewrite history.
  price_cents     INT        NOT NULL DEFAULT 0,

  is_active       TINYINT(1) NOT NULL DEFAULT 1,

  active_event_id BIGINT GENERATED ALWAYS AS
    (CASE WHEN is_active = 1 THEN event_id ELSE NULL END) VIRTUAL,
  active_seat_id  BIGINT GENERATED ALWAYS AS
    (CASE WHEN is_active = 1 THEN seat_id  ELSE NULL END) VIRTUAL,

  created_at      DATETIME   NOT NULL DEFAULT (NOW()),

  PRIMARY KEY (id),

  -- The guarantee.
  UNIQUE KEY uq_booking_seats_active (active_event_id, active_seat_id),

  KEY ix_booking_seats_seat (seat_id),
  KEY ix_booking_seats_booking (booking_id),
  KEY ix_booking_seats_event_active (event_id, is_active),

  CONSTRAINT fk_booking_seats_booking FOREIGN KEY (booking_id)
    REFERENCES bookings (id) ON DELETE CASCADE,
  CONSTRAINT fk_booking_seats_seat FOREIGN KEY (seat_id)
    REFERENCES seats (id) ON DELETE CASCADE,
  CONSTRAINT fk_booking_seats_event FOREIGN KEY (event_id)
    REFERENCES events (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
