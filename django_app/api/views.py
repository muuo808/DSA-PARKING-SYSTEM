"""API layer - versioned JSON endpoints under /api/v1/.

Read-only resources for anything that wants data instead of HTML: gate
display hardware, reporting tools, or a future mobile app. They return the
*current* state of the database, so another client sees exactly the values
the HTML screens show.

Access: the descriptor is public (it advertises no data), but every data
endpoint requires a signed-in staff session. Number plates and payment
records are operational data - and plates are personal data under the Kenya
Data Protection Act, 2019 - so none of it is anonymous. The public
availability screen reads Module 10's `/display` instead.
"""

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET

from django_app.parking.models import (
    ParkingSession,
    ParkingSlot,
    SessionStatus,
    Vehicle,
)
from django_app.payments.models import Payment


def api_root(request: HttpRequest) -> JsonResponse:
    """Service descriptor so clients can discover available resources."""
    return JsonResponse(
        {
            "service": "autopark-api",
            "version": "v1",
            "resources": [
                {"path": "/api/v1/slots/", "description": "Parking slots + live counts"},
                {"path": "/api/v1/vehicles/", "description": "Registered vehicles"},
                {"path": "/api/v1/sessions/", "description": "Entry/exit sessions"},
                {"path": "/api/v1/payments/", "description": "Payment records"},
            ],
            "status": "ok",
        }
    )


@login_required
@require_GET
def slots(request: HttpRequest) -> JsonResponse:
    """Module 2 - every bay and its live state, ordered as the display shows."""
    results = [
        {"id": s.id, "slot_number": s.slot_number, "status": s.status}
        for s in ParkingSlot.objects.order_by("slot_number")
    ]
    available = sum(1 for s in results if s["status"] == "AVAILABLE")
    return JsonResponse(
        {
            "count": len(results),
            "available": available,
            "occupied": len(results) - available,
            "results": results,
        }
    )


@login_required
@require_GET
def vehicles(request: HttpRequest) -> JsonResponse:
    """Module 3 - vehicles seen at the gate (plate stored normalised)."""
    results = [
        {
            "id": v.id,
            "plate_number": v.plate_number,
            "vehicle_type": v.vehicle_type,
        }
        for v in Vehicle.objects.order_by("plate_number")
    ]
    return JsonResponse({"count": len(results), "results": results})


@login_required
@require_GET
def sessions(request: HttpRequest) -> JsonResponse:
    """
    Module 4 - parking sessions, newest first.

    ``?status=ACTIVE`` (or ``COMPLETED``) filters server-side; an unknown
    value is ignored rather than breaking a client that guesses.
    """
    qs = ParkingSession.objects.select_related("vehicle", "slot").order_by(
        "-entry_time"
    )
    status_filter = request.GET.get("status", "").strip().upper()
    if status_filter in SessionStatus.values:
        qs = qs.filter(status=status_filter)

    results = [
        {
            "id": s.id,
            "plate_number": s.vehicle.plate_number,
            "vehicle_type": s.vehicle.vehicle_type,
            "slot": s.slot.slot_number,
            "entry_time": s.entry_time,
            "exit_time": s.exit_time,
            "duration_minutes": s.duration_minutes,
            "amount_paid": s.amount_paid,
            "status": s.status,
        }
        for s in qs
    ]
    return JsonResponse({"count": len(results), "results": results})


@login_required
@require_GET
def payments(request: HttpRequest) -> JsonResponse:
    """
    Module 6 - payment records, newest first.

    Amounts come back as decimal strings (``"50.00"``): Django's JSON encoder
    refuses to turn ``Decimal`` into ``float``, so revenue never gains a
    rounding error on the wire.
    """
    qs = Payment.objects.select_related("parking_session__vehicle").order_by(
        "-created_at"
    )
    results = [
        {
            "id": p.id,
            "session_id": p.parking_session_id,
            "plate_number": p.parking_session.vehicle.plate_number,
            "amount": p.amount,
            "payment_method": p.payment_method,
            "payment_status": p.payment_status,
            "paid_at": p.paid_at,
        }
        for p in qs
    ]
    return JsonResponse({"count": len(results), "results": results})
