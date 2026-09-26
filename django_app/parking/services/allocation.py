"""Slot allocation service - Module 2/3: automatic slot assignment."""

from django.db import connection, transaction

from django_app.parking.models import ParkingSlot, SlotStatus


def allocate_slot() -> ParkingSlot | None:
    """
    Allocate the next AVAILABLE slot and mark it OCCUPIED.

    Returns the allocated slot, or ``None`` when the car park is full.

    Concurrency: on backends that support it (PostgreSQL/Supabase) the
    row is locked with SELECT ... FOR UPDATE inside a transaction so two
    attendants can never be handed the same slot.
    """
    with transaction.atomic():
        candidates = ParkingSlot.objects.filter(
            status=SlotStatus.AVAILABLE
        ).order_by("slot_number")

        if connection.features.has_select_for_update:
            candidates = candidates.select_for_update()

        slot = candidates.first()
        if slot is None:
            return None

        slot.status = SlotStatus.OCCUPIED
        slot.save(update_fields=["status"])
        return slot


def release_slot(slot: ParkingSlot) -> ParkingSlot:
    """
    Free an occupied slot when its vehicle exits.

    Slots that are RESERVED or OUT_OF_SERVICE are left untouched - only
    an attendant/admin changes those states.
    """
    with transaction.atomic():
        locked = ParkingSlot.objects.get(pk=slot.pk)
        if connection.features.has_select_for_update:
            locked = ParkingSlot.objects.select_for_update().get(pk=slot.pk)

        if locked.status == SlotStatus.OCCUPIED:
            locked.status = SlotStatus.AVAILABLE
            locked.save(update_fields=["status"])

        return locked
