"""Unit tests: slot allocation, vehicle/session rules, payments (Django)."""

from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from django_app.accounts.models import User, UserRole
from django_app.parking.models import (
    ParkingSession,
    ParkingSlot,
    SessionStatus,
    SlotStatus,
    Vehicle,
    VehicleType,
)
from django_app.parking.services import allocate_slot, occupancy_summary, release_slot
from django_app.payments.models import Payment, PaymentMethod, PaymentStatus


class SlotAllocationTests(TestCase):
    """Module 2/3: automatic slot allocation."""

    def test_allocates_lowest_available_slot(self):
        ParkingSlot.objects.create(slot_number="A02")
        ParkingSlot.objects.create(slot_number="A01")

        slot = allocate_slot()

        self.assertIsNotNone(slot)
        self.assertEqual(slot.slot_number, "A01")
        self.assertEqual(slot.status, SlotStatus.OCCUPIED)

    def test_skips_reserved_and_out_of_service(self):
        ParkingSlot.objects.create(slot_number="A01", status=SlotStatus.RESERVED)
        ParkingSlot.objects.create(
            slot_number="A02", status=SlotStatus.OUT_OF_SERVICE
        )
        ParkingSlot.objects.create(slot_number="A03")

        slot = allocate_slot()

        self.assertEqual(slot.slot_number, "A03")

    def test_returns_none_when_full(self):
        ParkingSlot.objects.create(slot_number="A01", status=SlotStatus.OCCUPIED)

        self.assertIsNone(allocate_slot())

    def test_release_slot_frees_occupied_slot(self):
        slot = ParkingSlot.objects.create(slot_number="A01", status=SlotStatus.OCCUPIED)

        released = release_slot(slot)

        released.refresh_from_db()
        self.assertEqual(released.status, SlotStatus.AVAILABLE)

    def test_release_does_not_touch_reserved_slot(self):
        slot = ParkingSlot.objects.create(slot_number="A01", status=SlotStatus.RESERVED)

        release_slot(slot)

        slot.refresh_from_db()
        self.assertEqual(slot.status, SlotStatus.RESERVED)


class OccupancySummaryTests(TestCase):
    """Module 2: available count shown immediately."""

    def test_counts_by_status(self):
        ParkingSlot.objects.create(slot_number="A01")
        ParkingSlot.objects.create(slot_number="A02", status=SlotStatus.OCCUPIED)
        ParkingSlot.objects.create(slot_number="A03", status=SlotStatus.RESERVED)
        ParkingSlot.objects.create(slot_number="A04", status=SlotStatus.OUT_OF_SERVICE)

        stats = occupancy_summary()

        self.assertEqual(stats["total_slots"], 4)
        self.assertEqual(stats["available"], 1)
        self.assertEqual(stats["occupied"], 1)
        self.assertEqual(stats["reserved"], 1)
        self.assertEqual(stats["out_of_service"], 1)


class VehicleTests(TestCase):
    """Module 3: plate numbers normalised, types validated."""

    def test_plate_number_normalised_to_canonical_form(self):
        vehicle = Vehicle.objects.create(
            plate_number="  kda 123x ", vehicle_type=VehicleType.CAR
        )
        # Whitespace removed, upper case: KDA 123X and kda123x are one vehicle
        self.assertEqual(vehicle.plate_number, "KDA123X")

    def test_duplicate_plate_rejected_regardless_of_format(self):
        Vehicle.objects.create(plate_number="KDA 123X")
        from django.db import IntegrityError

        # Same plate written differently must still collide
        with self.assertRaises(IntegrityError):
            Vehicle.objects.create(plate_number="  kda123x ")

    def test_vehicle_type_choices(self):
        self.assertEqual(
            [choice.value for choice in VehicleType],
            ["CAR", "SUV", "VAN", "TRUCK", "MOTORCYCLE"],
        )


class ParkingSessionTests(TestCase):
    """Module 3/4: session lifecycle fields."""

    def setUp(self):
        self.slot = ParkingSlot.objects.create(slot_number="A01")
        self.vehicle = Vehicle.objects.create(plate_number="KDA 123X")
        self.session = ParkingSession.objects.create(
            vehicle=self.vehicle, slot=self.slot
        )

    def test_new_session_is_active(self):
        self.assertEqual(self.session.status, SessionStatus.ACTIVE)
        self.assertTrue(self.session.is_active)

    def test_duration_so_far_counts_elapsed_minutes(self):
        self.session.entry_time = timezone.now() - timezone.timedelta(minutes=45)
        self.session.save(update_fields=["entry_time"])

        self.assertGreaterEqual(self.session.duration_minutes_so_far, 44)
        self.assertLessEqual(self.session.duration_minutes_so_far, 46)


class PaymentTests(TestCase):
    """Module 6: payment records and status tracking."""

    def setUp(self):
        self.slot = ParkingSlot.objects.create(slot_number="A01")
        self.vehicle = Vehicle.objects.create(plate_number="KDA 123X")
        self.session = ParkingSession.objects.create(
            vehicle=self.vehicle, slot=self.slot, amount_paid=100
        )

    def test_new_payment_is_pending(self):
        payment = Payment.objects.create(
            parking_session=self.session,
            amount=Decimal("100.00"),
            payment_method=PaymentMethod.MPESA,
        )
        self.assertEqual(payment.payment_status, PaymentStatus.PENDING)
        self.assertFalse(payment.is_paid)

    def test_paid_session_reports_is_paid(self):
        Payment.objects.create(
            parking_session=self.session,
            amount=Decimal("100.00"),
            payment_method=PaymentMethod.CASH,
            payment_status=PaymentStatus.PAID,
            paid_at=timezone.now(),
        )
        self.assertTrue(self.session.is_paid)


class UserRoleTests(TestCase):
    """Module 1: role-based access flags."""

    def test_admin_role_flag(self):
        admin = User.objects.create_user(username="admin1", role=UserRole.ADMIN)
        self.assertTrue(admin.is_admin_role)
        self.assertFalse(admin.is_attendant_role)

    def test_attendant_role_flag(self):
        attendant = User.objects.create_user(
            username="att1", password="pass", role=UserRole.ATTENDANT
        )
        self.assertTrue(attendant.is_attendant_role)
        self.assertFalse(attendant.is_admin_role)

    def test_superuser_counts_as_admin(self):
        superuser = User.objects.create_superuser(
            username="root", password="pass", role=UserRole.ATTENDANT
        )
        self.assertTrue(superuser.is_admin_role)

    def test_passwords_never_stored_plain(self):
        user = User.objects.create_user(
            username="plain", password="secret-password-123"
        )
        self.assertNotIn("secret-password-123", user.password)
        self.assertTrue(user.check_password("secret-password-123"))
