"""Module 7 - barrier orchestration used by the entry/exit views."""

from typing import Any

from .clients import close_barrier, open_barrier
from .exceptions import BarrierServiceUnavailableError


def open_gate() -> tuple[bool, str]:
    """
    Issue the OPEN command to the (simulated) boom barrier.

    Returns ``(succeeded, detail)`` and never raises: the parking record
    is already committed when the gate is commanded, so a down barrier
    service surfaces as a warning to the attendant, not a failed exit.
    """
    return _command(open_barrier)


def close_gate() -> tuple[bool, str]:
    """Issue the CLOSE command to the barrier."""
    return _command(close_barrier)


def _command(action: Any) -> tuple[bool, str]:
    try:
        payload = action()
    except BarrierServiceUnavailableError as exc:
        return False, str(exc)
    return True, str(payload.get("barrier", "ok"))
