"""Service layer for parking operations (spec: service layer pattern)."""

from .allocation import allocate_slot, release_slot
from .barrier import open_gate  # noqa: F401  (re-exported for views/tests)
from .entry import normalise_plate, register_entry
from .exceptions import (
    BarrierServiceUnavailableError,
    FeeServiceUnavailableError,
    NoActiveSessionError,
    ParkingLotFullError,
    ParkingSystemError,
    VehicleAlreadyParkedError,
)
from .exit import get_active_session, quote_fee, register_exit
from .occupancy import occupancy_summary

__all__ = [
    "allocate_slot",
    "release_slot",
    "occupancy_summary",
    "register_entry",
    "register_exit",
    "quote_fee",
    "get_active_session",
    "normalise_plate",
    "open_gate",
    "ParkingSystemError",
    "ParkingLotFullError",
    "VehicleAlreadyParkedError",
    "NoActiveSessionError",
    "FeeServiceUnavailableError",
    "BarrierServiceUnavailableError",
]
