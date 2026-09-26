"""Dashboard and public display views (Modules 8 and 10)."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.http import require_GET

from django_app.parking.services import occupancy_summary

from .services import dashboard_statistics, trend_series


@login_required
@require_GET
def home(request):
    """Statistics cards and the 7-day trend chart (Modules 8 and 9 data)."""
    context = {
        "page_title": "Dashboard",
        "stats": dashboard_statistics(),
        "trend": trend_series(days=7),
    }
    return render(request, "dashboard/home.html", context)


@require_GET
def display(request):
    """
    Public availability screen (Module 10) at /display.

    No login required - intended for an LED display at the gate. The page
    reloads itself every 10 seconds via <meta http-equiv="refresh">.
    """
    context = {
        "stats": occupancy_summary(),
        "refresh_seconds": 10,
    }
    return render(request, "dashboard/display.html", context)
