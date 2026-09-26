"""Admin site configuration for slots, vehicles and sessions."""

from django.contrib import admin

from .models import ParkingSession, ParkingSlot, Vehicle


@admin.register(ParkingSlot)
class ParkingSlotAdmin(admin.ModelAdmin):
    list_display = ("slot_number", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("slot_number",)


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ("plate_number", "vehicle_type", "created_at")
    list_filter = ("vehicle_type",)
    search_fields = ("plate_number",)


@admin.register(ParkingSession)
class ParkingSessionAdmin(admin.ModelAdmin):
    list_display = (
        "vehicle",
        "slot",
        "entry_time",
        "exit_time",
        "duration_minutes",
        "amount_paid",
        "status",
    )
    list_filter = ("status", "entry_time")
    search_fields = ("vehicle__plate_number", "slot__slot_number")
    readonly_fields = ("created_at",)
