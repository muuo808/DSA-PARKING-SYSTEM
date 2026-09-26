"""Domain exceptions for parking operations (service layer contract)."""


class ParkingSystemError(Exception):
    """Base class for parking domain errors."""


class ParkingLotFullError(ParkingSystemError):
    """No AVAILABLE slot could be allocated."""


class VehicleAlreadyParkedError(ParkingSystemError):
    """The vehicle already has an ACTIVE parking session."""


class NoActiveSessionError(ParkingSystemError):
    """No ACTIVE session found for the given vehicle/session id."""


class FeeServiceUnavailableError(ParkingSystemError):
    """The Flask fee calculation service could not be reached."""


class BarrierServiceUnavailableError(ParkingSystemError):
    """The Flask barrier control service could not be reached."""
