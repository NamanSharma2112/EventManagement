#!/usr/bin/env python3
"""Fire N simultaneous booking requests at the same seat over HTTP.

This is the live demo: it talks to a running API exactly like a browser would,
so it proves the guarantee end to end rather than at the service layer.

    # terminal 1
    uvicorn app.main:app --port 8000

    # terminal 2
    python scripts/concurrency_demo.py                  # 10 racers, 1 seat
    python scripts/concurrency_demo.py --racers 25
    python scripts/concurrency_demo.py --seats 3        # overlapping group bookings

Exit code is 0 when exactly one request won, 1 otherwise -- so it doubles as a
smoke test in CI.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Barrier

DEFAULT_BASE_URL = "http://127.0.0.1:8000"


def request(method: str, url: str, payload: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url, data=data, method=method, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            body = response.read().decode()
            return response.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        return exc.code, json.loads(body) if body else {}


def create_demo_event(base_url: str, columns: int) -> dict:
    status, event = request(
        "POST",
        f"{base_url}/api/events",
        {
            "name": f"Concurrency Demo {datetime.now():%H:%M:%S}",
            "event_date": (datetime.now() + timedelta(days=7)).isoformat(
                timespec="seconds"
            ),
            "venue": "Race Condition Hall",
            "rows": 1,
            "columns": columns,
            "default_price_cents": 25000,
        },
    )
    if status != 201:
        sys.exit(f"Could not create the demo event ({status}): {event}")
    return event


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument(
        "--racers", type=int, default=10, help="simultaneous booking requests"
    )
    parser.add_argument(
        "--seats", type=int, default=1, help="seats each request asks for"
    )
    parser.add_argument(
        "--event-id",
        type=int,
        help="race against an existing event instead of creating one",
    )
    args = parser.parse_args()

    status, _ = request("GET", f"{args.base_url}/health")
    if status != 200:
        sys.exit(f"API is not answering at {args.base_url} -- start uvicorn first.")

    if args.event_id:
        event_id = args.event_id
    else:
        event_id = create_demo_event(args.base_url, max(args.seats, 1))["id"]

    _, seat_map = request("GET", f"{args.base_url}/api/events/{event_id}/seats")
    available = [
        seat
        for row in seat_map["rows"]
        for seat in row["seats"]
        if seat["status"] == "AVAILABLE"
    ][: args.seats]
    if len(available) < args.seats:
        sys.exit(f"Event {event_id} does not have {args.seats} available seats.")

    seat_ids = [seat["id"] for seat in available]
    labels = ", ".join(seat["label"] for seat in available)

    print(
        f"\n{args.racers} requests, all launched at once, all asking for seat(s) "
        f"{labels} of event {event_id}.\n"
    )

    # A barrier keeps every thread parked until the last one arrives, so the
    # requests hit the server together instead of trickling in.
    barrier = Barrier(args.racers)

    def race(index: int) -> tuple[int, str, dict]:
        barrier.wait(timeout=30)
        status, body = request(
            "POST",
            f"{args.base_url}/api/bookings",
            {
                "event_id": event_id,
                "seat_ids": seat_ids,
                "booker_name": f"Racer {index}",
                "booker_email": f"racer{index}@example.com",
            },
        )
        return index, str(status), body

    with ThreadPoolExecutor(max_workers=args.racers) as pool:
        results = sorted(pool.map(race, range(args.racers)))

    for index, status, body in results:
        if status == "201":
            print(f"  racer {index:>3}  201 CREATED   booked {labels} "
                  f"(ref {body['reference']})")
        else:
            print(f"  racer {index:>3}  {status} CONFLICT  {body.get('detail', body)}")

    tally = Counter(status for _, status, _ in results)
    winners = tally.get("201", 0)

    _, after = request("GET", f"{args.base_url}/api/events/{event_id}/seats")
    booked_now = {
        seat["label"]
        for row in after["rows"]
        for seat in row["seats"]
        if seat["status"] == "BOOKED"
    }

    print(f"\n  results: {dict(tally)}")
    print(f"  seats booked in the database afterwards: {sorted(booked_now) or 'none'}")

    if winners == 1:
        print("\n  PASS -- exactly one request won; every other one got 409.\n")
        return 0
    print(f"\n  FAIL -- expected exactly 1 successful booking, got {winners}.\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
