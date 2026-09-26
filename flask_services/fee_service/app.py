"""
SmartPark Kenya – Parking Fee Calculation Service (Flask microservice).

Endpoint required by Module 5:

    POST /api/calculate-fee
    {"entry_time": "2026-06-21T10:00:00", "exit_time": "2026-06-21T13:00:00"}
    ->
    {"duration_minutes": 180, "fee": 100}

Parking charges (spec table):

    Up to 30 mins   KES 0
    Up to 2 hours   KES 50
    Up to 4 hours   KES 100
    Up to 6 hours   KES 300
    Above 6 hours   KES 500

Run:  python flask_services/fee_service/app.py   (port 5000)
"""

import os
from datetime import datetime
from decimal import Decimal

from flask import Flask, jsonify, request

app = Flask(__name__)

# (upper bound in minutes, fee in KES) - checked in order, first match wins
FEE_BRACKETS: list[tuple[int, Decimal]] = [
    (30, Decimal("0")),
    (120, Decimal("50")),
    (240, Decimal("100")),
    (360, Decimal("300")),
    (10**9, Decimal("500")),  # above 6 hours
]

TIME_FORMATS = ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f")


def parse_datetime(value: str) -> datetime:
    """Parse an ISO-8601 timestamp from the request payload."""
    for fmt in TIME_FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise ValueError(f"Unrecognised datetime: {value!r} (expected e.g. 2026-06-21T10:00:00)")


def calculate_duration_minutes(entry_time: datetime, exit_time: datetime) -> int:
    """Whole minutes between entry and exit (never negative)."""
    seconds = (exit_time - entry_time).total_seconds()
    if seconds < 0:
        raise ValueError("exit_time cannot be before entry_time")
    return int(seconds // 60)


def calculate_fee(duration_minutes: int) -> Decimal:
    """Map a duration in minutes onto the parking charge table."""
    if duration_minutes < 0:
        raise ValueError("duration_minutes cannot be negative")
    for upper_bound, fee in FEE_BRACKETS:
        if duration_minutes <= upper_bound:
            return fee
    raise AssertionError("unreachable - final bracket is unbounded")  # pragma: no cover


def price_session(entry_time: datetime, exit_time: datetime) -> dict[str, int]:
    """Duration + fee for one parking session."""
    duration = calculate_duration_minutes(entry_time, exit_time)
    return {"duration_minutes": duration, "fee": int(calculate_fee(duration))}


@app.get("/api/health")
def health():
    return jsonify({"service": "fee-service", "status": "ok"})


@app.post("/api/calculate-fee")
def calculate_fee_endpoint():
    payload = request.get_json(silent=True) or {}
    entry_raw, exit_raw = payload.get("entry_time"), payload.get("exit_time")

    if not entry_raw or not exit_raw:
        return jsonify({"error": "entry_time and exit_time are required"}), 400

    try:
        entry_time = parse_datetime(entry_raw)
        exit_time = parse_datetime(exit_raw)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    try:
        result = price_session(entry_time, exit_time)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(result)


if __name__ == "__main__":
    # FLASK_HOST=0.0.0.0 inside Docker so the service is reachable from
    # other containers; defaults to loopback for local development.
    app.run(
        host=os.environ.get("FLASK_HOST", "127.0.0.1"),
        port=int(os.environ.get("FEE_SERVICE_PORT", 5000)),
    )
