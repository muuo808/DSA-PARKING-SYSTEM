"""Module 9 - Reports: revenue, occupancy and the session ledger."""

import csv

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET

from django_app.accounts.decorators import admin_required

from .services import (
    headline_figures,
    occupancy_breakdown,
    recent_sessions,
    revenue_by_method,
    revenue_series,
    session_ledger,
)


@admin_required
@require_GET
def report_index(request: HttpRequest) -> HttpResponse:
    """
    Management report (admin only): KPIs, 14-day revenue trend, revenue by
    payment method, slot occupancy breakdown and the recent session ledger.
    """
    context = {
        "page_title": "Reports",
        "figures": headline_figures(),
        "series": revenue_series(days=14),
        "methods": revenue_by_method(),
        "occupancy": occupancy_breakdown(),
        "sessions": recent_sessions(limit=25),
        "generated_at": timezone.localtime(),
    }
    return render(request, "reports/report.html", context)


@admin_required
@require_GET
def export_sessions(request: HttpRequest) -> HttpResponse:
    """Download the full session ledger as CSV (Excel-friendly)."""
    rows = session_ledger()
    today = timezone.localtime().strftime("%Y%m%d-%H%M")

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="parking-sessions-{today}.csv"'
    response.write("\ufeff")  # BOM so Excel reads the UTF-8 correctly

    writer = csv.writer(response)
    writer.writerow(
        [
            "Plate",
            "Vehicle type",
            "Slot",
            "Entry",
            "Exit",
            "Duration (min)",
            "Amount (KES)",
            "Status",
            "Registered by",
        ]
    )
    for session in rows:
        writer.writerow(
            [
                session.vehicle.plate_number,
                session.vehicle.get_vehicle_type_display(),
                session.slot.slot_number,
                session.entry_time.strftime("%Y-%m-%d %H:%M"),
                session.exit_time.strftime("%Y-%m-%d %H:%M") if session.exit_time else "",
                session.duration_minutes if session.duration_minutes is not None else "",
                session.amount_paid,
                session.get_status_display(),
                session.registered_by.username if session.registered_by else "",
            ]
        )
    return response
