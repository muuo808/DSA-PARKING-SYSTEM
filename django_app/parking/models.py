"""Parking slots, vehicles and parking sessions (Modules 2, 3 and 4)."""

from django.conf import settings
from django.db import models
from django.utils import timezone


class SlotStatus(models.TextChoices):
    """Status values required by Module 2."""

    AVAILABLE = "AVAILABLE", "Available"
    OCCUPIED = "OCCUPIED", "Occupied"
    RESERVED = "RESERVED", "Reserved"
    OUT_OF_SERVICE = "OUT_OF_SERVICE", "Out of service"


class VehicleType(models.TextChoices):
    """Vehicle types required by Module 3."""

    CAR = "CAR", "Car"
    SUV = "SUV", "SUV"
    VAN = "VAN", "Van"
    TRUCK = "TRUCK", "Truck"
    MOTORCYCLE = "MOTORCYCLE", "Motorcycle"


class SessionStatus(models.TextChoices):
    """Parking session status values required by the schema."""

    ACTIVE = "ACTIVE", "Active"
    COMPLETED = "COMPLETED", "Completed"


class ParkingSlot(models.Model):
    """
    A single physical parking space. Maps to ``parking_slots``.
    """

    slot_number = models.CharField(max_length=10, unique=True)
    status = models.CharField(
        max_length=20,
        choices=SlotStatus.choices,
        default=SlotStatus.AVAILABLE,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["slot_number"]
        verbose_name = "parking slot"

    def __str__(self) -> str:
        return f"Slot {self.slot_number}"

    @property
    def is_available(self) -> bool:
        return self.status == SlotStatus.AVAILABLE


def normalise_plate(plate_number: str) -> str:
    """
    Canonical plate form: upper case with no whitespace.

    ``'  kda 123x '`` -> ``'KDA123X'``. Because the form is
    whitespace-insensitive, ``KDA 123X`` and ``KDA123X`` can never become
    two vehicle records for the same car (which would defeat duplicate
    entry detection).
    """
    return "".join(plate_number.split()).upper()


class Vehicle(models.Model):
    """A vehicle that can park. Maps to ``vehicles``."""

    plate_number = models.CharField(max_length=20, unique=True)
    vehicle_type = models.CharField(
        max_length=20,
        choices=VehicleType.choices,
        default=VehicleType.CAR,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["plate_number"]
        verbose_name = "vehicle"

    def __str__(self) -> str:
        return self.plate_number

    def save(self, *args: object, **kwargs: object) -> None:
        """Store plates in canonical form (``kda 123x`` -> ``KDA123X``)."""
        self.plate_number = normalise_plate(self.plate_number)
        super().save(*args, **kwargs)


class ParkingSession(models.Model):
    """
    One entry->exit stay of a vehicle in a slot.
    Maps to ``parking_sessions``.
    """

    vehicle = models.ForeignKey(
        Vehicle,
        on_delete=models.PROTECT,
        related_name="sessions",
    )
    slot = models.ForeignKey(
        ParkingSlot,
        on_delete=models.PROTECT,
        related_name="sessions",
    )
    # The brief: "records vehicles on arrival" - this timestamp is the start
    # of every fee calculation (algorithm A1 measures from here).
    entry_time = models.DateTimeField(default=timezone.now)
    # Set once, at exit, together with duration_minutes and amount_paid.
    exit_time = models.DateTimeField(null=True, blank=True)
    duration_minutes = models.PositiveIntegerField(null=True, blank=True)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    # ACTIVE -> COMPLETED is a one-way transition handled by register_exit.
    status = models.CharField(
        max_length=20,
        choices=SessionStatus.choices,
        default=SessionStatus.ACTIVE,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    registered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="registered_sessions",
        null=True,
        blank=True,
        help_text="Attendant who recorded the entry.",
    )

    class Meta:
        ordering = ["-entry_time"]
        verbose_name = "parking session"

    def __str__(self) -> str:
        return f"{self.vehicle.plate_number} @ {self.slot.slot_number}"

    @property
    def is_active(self) -> bool:
        return self.status == SessionStatus.ACTIVE

    @property
    def duration_minutes_so_far(self) -> int:
        """Elapsed minutes for an active session (live duration display)."""
        end = self.exit_time or timezone.now()
        return max(0, int((end - self.entry_time).total_seconds() // 60))

    @property
    def is_paid(self) -> bool:
        """True once a completed payment exists for this session."""
        return self.payments.filter(payment_status="PAID").exists()
