"""Module 4 - Vehicle exit: duration, fee, payment, slot release."""

from datetime import datetime
from decimal import Decimal

from django.contrib.auth.models import AbstractBaseUser
from django.db import connection, transaction
from django.utils import timezone

from django_app.parking.models import ParkingSession, SessionStatus
from django_app.payments.models import Payment, PaymentMethod, PaymentStatus

from .allocation import release_slot
from .clients import calculate_fee
from .exceptions import NoActiveSessionError
from .entry import normalise_plate


def get_active_session(plate_number: str) -> ParkingSession | None:
    """Module 4 step 1–2: search the plate and retrieve its ACTIVE session."""
    plate = normalise_plate(plate_number)
    if not plate:
        return None
    return (
        ParkingSession.objects.select_related("vehicle", "slot")
        .filter(vehicle__plate_number=plate, status=SessionStatus.ACTIVE)
        .first()
    )


def quote_fee(session: ParkingSession, at: datetime | None = None) -> tuple[int, Decimal]:
    """
    Module 4 steps 3–4 (preview): duration + fee for an in-progress session.

    Delegates to the Flask fee service. Raises FeeServiceUnavailableError
    when that service is down - callers surface it to the attendant.
    """
    exit_time = at or timezone.now()
    return calculate_fee(session.entry_time, exit_time)


def register_exit(
    session_id: int,
    payment_method: str,
    user: AbstractBaseUser | None = None,
) -> tuple[ParkingSession, Payment]:
    """
    Module 4 steps 3–7 in one atomic operation:

    3. Calculate duration
    4. Calculate fee (Flask fee service - REST call)
    5. Process payment
    6. Record exit time
    7. Release the slot

    The barrier OPEN command is issued by the view *after* commit
    (step 8) - hardware side effects never roll back a transaction.

    Raises:
        NoActiveSessionError        – session missing or already exited
        FeeServiceUnavailableError  – Flask fee service down (nothing committed)
    """
    session = (
        ParkingSession.objects.select_related("vehicle", "slot")
        .filter(pk=session_id, status=SessionStatus.ACTIVE)
        .first()
    )
    if session is None:
        raise NoActiveSessionError(f"No active parking session #{session_id}.")

    exit_time = timezone.now()

    # Step 3 + 4: duration and fee are computed BEFORE any write, so a
    # down fee service leaves the database untouched.
    duration_minutes = int((exit_time - session.entry_time).total_seconds() // 60)
    _duration, fee = calculate_fee(session.entry_time, exit_time)
    if _duration != duration_minutes:
        duration_minutes = _duration  # trust the fee service as source of truth

    if payment_method not in PaymentMethod.values:
        raise ValueError(f"Invalid payment method: {payment_method!r}")

    with transaction.atomic():
        locked = ParkingSession.objects.select_for_update().get(pk=session.pk) \
            if connection.features.has_select_for_update else session
        if locked.status != SessionStatus.ACTIVE:
            raise NoActiveSessionError(
                f"Session #{session.pk} was already completed."
            )

        payment = Payment.objects.create(
            parking_session=locked,
            amount=fee,
            payment_method=payment_method,
            payment_status=PaymentStatus.PAID,
            paid_at=exit_time,
            received_by=user if isinstance(user, AbstractBaseUser) else None,
        )

        locked.exit_time = exit_time
        locked.duration_minutes = duration_minutes
        locked.amount_paid = fee
        locked.status = SessionStatus.COMPLETED
        locked.save(
            update_fields=["exit_time", "duration_minutes", "amount_paid", "status"]
        )

        release_slot(locked.slot)

    return locked, payment
