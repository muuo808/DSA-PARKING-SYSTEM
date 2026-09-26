"""Reporting aggregations for Module 9 (revenue, occupancy, session ledger)."""

from datetime import timedelta
from decimal import Decimal

from django.db.models import Avg, Count, Sum
from django.utils import timezone

from django_app.parking.models import ParkingSession, ParkingSlot, SessionStatus
from django_app.payments.models import Payment, PaymentMethod, PaymentStatus

METHOD_LABELS = dict(PaymentMethod.choices)


def revenue_series(days: int = 14) -> list[dict]:
    """
    Paid revenue per day for the last ``days`` days, oldest first.

    Days without payments are filled with zero so charts keep a continuous
    x-axis. Amounts are floats - the payload is bound straight into a
    Chart.js config in the template.
    """
    today = timezone.localdate()
    start = today - timedelta(days=days - 1)

    rows = {
        row["paid_at__date"]: row
        for row in Payment.objects.filter(
            payment_status=PaymentStatus.PAID,
            paid_at__date__gte=start,
        )
        .values("paid_at__date")
        .annotate(total=Sum("amount"), count=Count("id"))
    }

    series: list[dict] = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        row = rows.get(day)
        total = row["total"] if row else Decimal("0")
        series.append(
            {
                "date": day.isoformat(),
                "label": day.strftime("%d %b"),
                "revenue": float(total or 0),
                "payments": int(row["count"] if row else 0),
            }
        )
    return series


def revenue_by_method() -> list[dict]:
    """Paid totals grouped by payment method (M-Pesa, cash, card)."""
    rows = (
        Payment.objects.filter(payment_status=PaymentStatus.PAID)
        .values("payment_method")
        .annotate(total=Sum("amount"), count=Count("id"))
        .order_by("-total")
    )
    return [
        {
            "code": row["payment_method"],
            "label": METHOD_LABELS.get(row["payment_method"], row["payment_method"]),
            "total": float(row["total"] or 0),
            "count": int(row["count"]),
        }
        for row in rows
    ]


def headline_figures() -> dict[str, object]:
    """The KPI block: revenue (all time / month / today) and session stats."""
    today = timezone.localdate()
    paid = Payment.objects.filter(payment_status=PaymentStatus.PAID)

    revenue_total = paid.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    revenue_month = (
        paid.filter(paid_at__year=today.year, paid_at__month=today.month).aggregate(
            total=Sum("amount")
        )["total"]
        or Decimal("0")
    )
    revenue_today = (
        paid.filter(paid_at__date=today).aggregate(total=Sum("amount"))["total"]
        or Decimal("0")
    )

    sessions = ParkingSession.objects
    completed = sessions.filter(status=SessionStatus.COMPLETED)
    average_duration = (
        completed.aggregate(avg=Avg("duration_minutes"))["avg"] or 0
    )

    return {
        "revenue_total": float(revenue_total),
        "revenue_month": float(revenue_month),
        "revenue_today": float(revenue_today),
        "payments_total": paid.count(),
        "sessions_total": sessions.count(),
        "sessions_completed": completed.count(),
        "sessions_active": sessions.filter(status=SessionStatus.ACTIVE).count(),
        "sessions_today": sessions.filter(entry_time__date=today).count(),
        "average_duration": int(average_duration),
        "revenue_per_session": float(
            (revenue_total / completed.count()) if completed.count() else 0
        ),
    }


def occupancy_breakdown() -> list[dict]:
    """Slot counts per status with human labels (for the occupancy table)."""
    labels = dict(ParkingSlot._meta.get_field("status").choices)
    counts = {
        row["status"]: row["n"]
        for row in ParkingSlot.objects.values("status").annotate(n=Count("id"))
    }
    total = sum(counts.values()) or 1
    breakdown = []
    for code, label in labels.items():
        count = counts.get(code, 0)
        breakdown.append(
            {
                "code": code,
                "label": label,
                "count": count,
                "percent": round(100 * count / total, 1),
            }
        )
    return breakdown


def recent_sessions(limit: int = 25) -> list[ParkingSession]:
    """Latest sessions with everything the ledger table needs to render."""
    return list(
        ParkingSession.objects.select_related(
            "vehicle", "slot", "registered_by"
        ).order_by("-entry_time")[:limit]
    )


def session_ledger() -> list[ParkingSession]:
    """Every session, for the CSV export."""
    return list(
        ParkingSession.objects.select_related(
            "vehicle", "slot", "registered_by"
        ).order_by("-entry_time")
    )
