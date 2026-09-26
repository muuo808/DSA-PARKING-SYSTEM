"""Dashboard statistics service (Module 8 statistics cards)."""

from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.utils import timezone

from django_app.parking.models import ParkingSession
from django_app.payments.models import Payment, PaymentStatus
from django_app.parking.services import occupancy_summary


def _revenue_for(day: date) -> Decimal:
    """Sum of PAID payments settled on the given day."""
    total = Payment.objects.filter(
        payment_status=PaymentStatus.PAID,
        paid_at__date=day,
    ).aggregate(total=Sum("amount"))["total"]
    return Decimal(total or 0)


def _revenue_for_month(day: date) -> Decimal:
    """Sum of PAID payments settled in the given month."""
    total = Payment.objects.filter(
        payment_status=PaymentStatus.PAID,
        paid_at__year=day.year,
        paid_at__month=day.month,
    ).aggregate(total=Sum("amount"))["total"]
    return Decimal(total or 0)


def dashboard_statistics() -> dict[str, object]:
    """
    Build the six statistic cards required by Module 8.

    Returns slot occupancy, today's vehicle activity and revenue totals.
    """
    today = timezone.localdate()

    vehicles_today = ParkingSession.objects.filter(entry_time__date=today).count()
    exits_today = ParkingSession.objects.filter(
        exit_time__date=today
    ).count()

    stats: dict[str, object] = occupancy_summary()
    stats.update(
        {
            "vehicles_today": vehicles_today,
            "exits_today": exits_today,
            "revenue_today": _revenue_for(today),
            "revenue_month": _revenue_for_month(today),
        }
    )
    return stats


def trend_series(days: int = 7) -> list[dict]:
    """
    Daily vehicle entries, exits and revenue for the last ``days`` days
    (oldest first) - the data behind the Module 8 trend chart.

    Days with no activity return zeros so the chart keeps a continuous
    x-axis. Revenue is a float: the payload is parsed with ``JSON.parse``
    in the template and handed straight to Chart.js.
    """
    today = timezone.localdate()
    start = today - timedelta(days=days - 1)

    entries = {
        row["entry_time__date"]: row["n"]
        for row in ParkingSession.objects.filter(entry_time__date__gte=start)
        .values("entry_time__date")
        .annotate(n=Count("id"))
    }
    exits = {
        row["exit_time__date"]: row["n"]
        for row in ParkingSession.objects.filter(
            exit_time__isnull=False, exit_time__date__gte=start
        )
        .values("exit_time__date")
        .annotate(n=Count("id"))
    }
    revenue = {
        row["paid_at__date"]: row["total"]
        for row in Payment.objects.filter(
            payment_status=PaymentStatus.PAID, paid_at__date__gte=start
        )
        .values("paid_at__date")
        .annotate(total=Sum("amount"))
    }

    series: list[dict] = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        series.append(
            {
                "date": day.isoformat(),
                "label": day.strftime("%a %d"),
                "entries": int(entries.get(day, 0)),
                "exits": int(exits.get(day, 0)),
                "revenue": float(revenue.get(day, 0) or 0),
            }
        )
    return series
