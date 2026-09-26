"""Views: slot management (Module 2), vehicle entry (3) and exit (4)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from django_app.accounts.decorators import admin_required
from django_app.payments.models import PaymentMethod

from .forms import ExitPaymentForm, ParkingSlotForm, VehicleEntryForm
from .models import ParkingSession, ParkingSlot, SessionStatus, SlotStatus
from .services import (
    FeeServiceUnavailableError,
    NoActiveSessionError,
    ParkingLotFullError,
    VehicleAlreadyParkedError,
    get_active_session,
    occupancy_summary,
    open_gate,
    quote_fee,
    register_entry,
    register_exit,
)

# ---------------------------------------------------------------- Module 2


@login_required
@require_GET
def slot_list(request: HttpRequest) -> HttpResponse:
    """Live occupancy overview plus the slot table."""
    context = {
        "page_title": "Parking Slots",
        "slots": ParkingSlot.objects.all(),
        "stats": occupancy_summary(),
        "status_choices": SlotStatus.choices,
        "form": ParkingSlotForm(),
        "can_manage": request.user.is_admin_role,
    }
    return render(request, "parking/slot_list.html", context)


@admin_required
@require_POST
def slot_create(request: HttpRequest) -> HttpResponse:
    """Create a parking slot (admin only)."""
    form = ParkingSlotForm(request.POST)
    if form.is_valid():
        slot = form.save()
        messages.success(request, f"Slot {slot.slot_number} created.")
    else:
        messages.error(request, "Could not create slot: check the details below.")
    return redirect("parking:slot_list")


@admin_required
@require_POST
def slot_update_status(request: HttpRequest, pk: int) -> HttpResponse:
    """Change a slot's status (admin only)."""
    slot = get_object_or_404(ParkingSlot, pk=pk)
    status = request.POST.get("status", "")

    if status not in SlotStatus.values:
        messages.error(request, "Invalid status value.")
        return redirect("parking:slot_list")

    # Guard: never flip an OCCUPIED slot manually while a session is active.
    if (
        slot.status == SlotStatus.OCCUPIED
        and status != SlotStatus.OCCUPIED
        and slot.sessions.filter(status=SessionStatus.ACTIVE).exists()
    ):
        messages.error(
            request,
            f"Slot {slot.slot_number} has an active session - register the exit instead.",
        )
        return redirect("parking:slot_list")

    slot.status = status
    slot.save(update_fields=["status"])
    messages.success(
        request, f"Slot {slot.slot_number} set to {slot.get_status_display()}."
    )
    return redirect("parking:slot_list")


# ---------------------------------------------------------------- Module 3


@login_required
@require_http_methods(["GET", "POST"])
def vehicle_entry(request: HttpRequest) -> HttpResponse:
    """
    Register an arriving vehicle.

    Workflow: show available slots -> plate + type -> allocate slot ->
    create session -> command barrier OPEN.
    """
    stats = occupancy_summary()

    if request.method == "POST":
        form = VehicleEntryForm(request.POST)
        if form.is_valid():
            try:
                session = register_entry(
                    plate_number=form.cleaned_data["plate_number"],
                    vehicle_type=form.cleaned_data["vehicle_type"],
                    user=request.user,
                )
            except (VehicleAlreadyParkedError, ParkingLotFullError) as exc:
                messages.error(request, str(exc))
                return redirect("parking:entry")

            gate_ok, gate_detail = open_gate()
            allocated = f"{session.vehicle.plate_number} allocated slot {session.slot.slot_number}"
            if gate_ok:
                messages.success(request, f"{allocated}. Barrier OPEN.")
            else:
                messages.warning(
                    request,
                    f"{allocated}, but the barrier did not respond ({gate_detail}).",
                )
            return redirect("parking:entry")

        messages.error(request, "Check the form and try again.")
        return redirect("parking:entry")

    today = timezone.localdate()
    context = {
        "page_title": "Vehicle Entry",
        "form": VehicleEntryForm(),
        "stats": stats,
        "recent_entries": ParkingSession.objects.select_related(
            "vehicle", "slot"
        )
        .filter(entry_time__date=today)
        .order_by("-entry_time")[:10],
        "payment_methods": PaymentMethod.choices,
    }
    return render(request, "parking/entry.html", context)


# ---------------------------------------------------------------- Module 4


@login_required
@require_http_methods(["GET", "POST"])
def vehicle_exit(request: HttpRequest) -> HttpResponse:
    """
    Handle a departing vehicle.

    GET  ?plate=      -> search the plate, show session + live fee quote
    POST session_id   -> process payment, record exit, release slot,
                         command barrier OPEN
    """
    session: ParkingSession | None = None
    fee_quote: tuple[int, object] | None = None
    quote_error: str | None = None
    plate_query = ""

    if request.method == "POST":
        form = ExitPaymentForm(request.POST)
        if form.is_valid():
            try:
                session, payment = register_exit(
                    session_id=form.cleaned_data["session_id"],
                    payment_method=form.cleaned_data["payment_method"],
                    user=request.user,
                )
            except NoActiveSessionError as exc:
                messages.error(request, str(exc))
                return redirect("parking:exit")
            except FeeServiceUnavailableError:
                messages.error(
                    request,
                    "Fee service is unavailable - no payment was recorded. "
                    "Start it with ./run_dev.sh and try again.",
                )
                return redirect("parking:exit")

            label = dict(PaymentMethod.choices)[payment.payment_method]
            summary = (
                f"KES {payment.amount} received via {label} for "
                f"{session.vehicle.plate_number} ({session.duration_minutes} min, "
                f"slot {session.slot.slot_number} released)"
            )
            # Payment is committed and the slot is free - only now does the
            # barrier open (the brief: open "on the payment of parking fees").
            gate_ok, gate_detail = open_gate()
            if gate_ok:
                messages.success(request, f"{summary}. Barrier OPEN.")
            else:
                messages.warning(
                    request, f"{summary}, but the barrier did not respond."
                )
            return redirect("parking:exit")

        messages.error(request, "Invalid payment submission.")
        return redirect("parking:exit")

    # GET: search by plate number
    plate_query = request.GET.get("plate", "").strip()
    if plate_query:
        session = get_active_session(plate_query)
        if session is None:
            messages.info(
                request, f"No active session found for '{plate_query.upper()}'."
            )
        else:
            try:
                fee_quote = quote_fee(session)
            except FeeServiceUnavailableError:
                quote_error = (
                    "Fee service is unavailable - the exit cannot be processed "
                    "until it is running."
                )

    context = {
        "page_title": "Vehicle Exit",
        "plate_query": plate_query,
        "session": session,
        "fee_quote": fee_quote,
        "quote_error": quote_error,
        "payment_methods": PaymentMethod.choices,
        "stats": occupancy_summary(),
        "active_sessions": ParkingSession.objects.select_related(
            "vehicle", "slot"
        )
        .filter(status=SessionStatus.ACTIVE)
        .order_by("-entry_time")[:20],
        "form": ExitPaymentForm(
            initial={"session_id": session.pk} if session else None
        ),
    }
    return render(request, "parking/exit.html", context)
