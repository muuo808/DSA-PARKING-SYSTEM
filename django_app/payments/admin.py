"""Admin site configuration for payments."""

from django.contrib import admin

from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "parking_session",
        "amount",
        "payment_method",
        "payment_status",
        "paid_at",
    )
    list_filter = ("payment_method", "payment_status")
    search_fields = ("parking_session__vehicle__plate_number",)
    readonly_fields = ("created_at",)
