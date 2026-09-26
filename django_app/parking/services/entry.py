"""Module 3 - Vehicle entry: automatic slot allocation + session creation."""

from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction
from django.utils import timezone

from django_app.parking.models import (
    ParkingSession,
    SessionStatus,
    Vehicle,
    VehicleType,
    normalise_plate,  # canonical plate form lives with the entity (re-exported)
)

from .allocation import allocate_slot
from .exceptions import ParkingLotFullError, VehicleAlreadyParkedError


def register_entry(
    plate_number: str,
    vehicle_type: str = VehicleType.CAR,
    user: AbstractBaseUser | None = None,
) -> ParkingSession:
    """
    Register an arriving vehicle (spec workflow steps 3–6):

    1. Normalise the plate number.
    2. Get or create the vehicle record.
    3. Reject if it already has an ACTIVE session (prevents double entry).
    4. Allocate the lowest AVAILABLE slot and mark it OCCUPIED.
    5. Create the ACTIVE parking session.

    Raising points:
        VehicleAlreadyParkedError – vehicle already inside
        ParkingLotFullError       – no slot available (step 2 display)
    """
    plate = normalise_plate(plate_number)  # UC-02: KDA 123X == KDA123X (A3)
    if not plate:
        raise ValueError("Plate number is required.")

    with transaction.atomic():
        vehicle, _created = Vehicle.objects.get_or_create(
            plate_number=plate,
            defaults={"vehicle_type": vehicle_type},
        )

        # Duplicate-entry guard: one ACTIVE session per vehicle, so a car
        # cannot occupy two slots or be counted twice in the statistics.
        already_parked = ParkingSession.objects.filter(
            vehicle=vehicle, status=SessionStatus.ACTIVE
        ).exists()
        if already_parked:
            raise VehicleAlreadyParkedError(
                f"{vehicle.plate_number} already has an active session."
            )

        # First-fit under a row lock (algorithm A2); None means the lot is
        # full, which the view surfaces as a message rather than a crash.
        slot = allocate_slot()
        if slot is None:
            raise ParkingLotFullError("No parking slot is currently available.")

        session = ParkingSession.objects.create(
            vehicle=vehicle,
            slot=slot,
            entry_time=timezone.now(),
            status=SessionStatus.ACTIVE,
            registered_by=user if isinstance(user, AbstractBaseUser) else None,
        )

    return session
