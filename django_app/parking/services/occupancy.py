"""Occupancy statistics used by the dashboard and public display."""

from django.db.models import Count, Q

from django_app.parking.models import ParkingSlot, SlotStatus


def occupancy_summary() -> dict[str, int]:
    """
    Live slot counts for Module 8 statistics cards and Module 10 display.

    Returns keys: total_slots, occupied, available, reserved, out_of_service.
    """
    counts = ParkingSlot.objects.aggregate(
        total_slots=Count("id"),
        occupied=Count("id", filter=Q(status=SlotStatus.OCCUPIED)),
        available=Count("id", filter=Q(status=SlotStatus.AVAILABLE)),
        reserved=Count("id", filter=Q(status=SlotStatus.RESERVED)),
        out_of_service=Count("id", filter=Q(status=SlotStatus.OUT_OF_SERVICE)),
    )
    return {key: int(value or 0) for key, value in counts.items()}
