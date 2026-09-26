"""Payment records (Module 6)."""

from decimal import Decimal

from django.db import models

from django_app.parking.models import ParkingSession


class PaymentMethod(models.TextChoices):
    """Payment methods required by Module 6."""

    CASH = "CASH", "Cash"
    MPESA = "MPESA", "M-Pesa"
    CARD = "CARD", "Card"


class PaymentStatus(models.TextChoices):
    """Lifecycle of a payment, extensible for M-Pesa STK callbacks later."""

    PENDING = "PENDING", "Pending"
    PAID = "PAID", "Paid"
    FAILED = "FAILED", "Failed"


class Payment(models.Model):
    """
    A payment against a parking session. Maps to ``payments``.

    The architecture reserves room for M-Pesa STK Push, payment gateways
    and QR flows: add a provider reference field when those land, the
    rest of the system already reads ``payment_status``.
    """

    parking_session = models.ForeignKey(
        ParkingSession,
        on_delete=models.PROTECT,
        related_name="payments",
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CASH,
    )
    payment_status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
    )
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    received_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="received_payments",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "payment"

    def __str__(self) -> str:
        return f"KES {self.amount} · {self.parking_session.vehicle.plate_number}"

    @property
    def is_paid(self) -> bool:
        return self.payment_status == PaymentStatus.PAID

    @property
    def amount_as_decimal(self) -> Decimal:
        return Decimal(self.amount)
