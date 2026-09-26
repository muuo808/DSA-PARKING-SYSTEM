"""
HTTP clients for the Flask microservices.

Django never talks to barrier/fee logic directly - those live in the
Flask services (REST contract per spec). Every call has a strict timeout
so a slow microservice can never hang a parking transaction.
"""

from datetime import datetime, timezone as dt_timezone
from decimal import Decimal
from typing import Any

import requests
from django.conf import settings

from .exceptions import BarrierServiceUnavailableError, FeeServiceUnavailableError

# The fee service expects naive ISO timestamps: 2026-06-21T10:00:00
TIME_FORMAT = "%Y-%m-%dT%H:%M:%S"


def _isoformat(value: datetime) -> str:
    """
    Serialise a datetime for the fee service.

    Duration is the difference between two instants, so both ends are
    normalised to UTC and stripped of offset/microseconds - sub-minute
    precision cannot affect the whole-minute fee brackets.
    """
    if value.tzinfo is not None:
        value = value.astimezone(dt_timezone.utc)
    value = value.replace(tzinfo=None, microsecond=0)
    return value.strftime(TIME_FORMAT)


def calculate_fee(entry_time: datetime, exit_time: datetime) -> tuple[int, Decimal]:
    """
    Call Flask fee service: POST {FEE_SERVICE_URL}/api/calculate-fee.

    Returns ``(duration_minutes, fee)``.
    Raises FeeServiceUnavailableError when the service is down or errors.
    """
    url = f"{settings.FEE_SERVICE_URL}/api/calculate-fee"
    try:
        response = requests.post(
            url,
            json={
                "entry_time": _isoformat(entry_time),
                "exit_time": _isoformat(exit_time),
            },
            timeout=settings.SERVICE_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        raise FeeServiceUnavailableError(
            f"Fee service unavailable at {url}: {exc}"
        ) from exc

    payload: dict[str, Any] = response.json()
    return int(payload["duration_minutes"]), Decimal(str(payload["fee"]))


def open_barrier() -> dict[str, Any]:
    """Call Flask barrier service: POST /api/barrier/open."""
    return _barrier_command("open")


def close_barrier() -> dict[str, Any]:
    """Call Flask barrier service: POST /api/barrier/close."""
    return _barrier_command("close")


def _barrier_command(command: str) -> dict[str, Any]:
    url = f"{settings.BARRIER_SERVICE_URL}/api/barrier/{command}"
    try:
        response = requests.post(url, timeout=settings.SERVICE_TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        raise BarrierServiceUnavailableError(
            f"Barrier service unavailable at {url}: {exc}"
        ) from exc
    return response.json()
