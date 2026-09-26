"""
Integration + end-to-end tests (spec: Testing Requirements).

- Unit level  : entry/exit services with the fee client mocked
- Integration : Django -> Flask over REAL HTTP (fee + barrier services)
- End-to-end  : vehicle entry, vehicle exit and payment through the views
"""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from django_app.parking.models import (
    ParkingSession,
    ParkingSlot,
    SessionStatus,
    SlotStatus,
    Vehicle,
)
from django_app.parking.services import (
    FeeServiceUnavailableError,
    NoActiveSessionError,
    ParkingLotFullError,
    VehicleAlreadyParkedError,
    get_active_session,
    register_entry,
    register_exit,
)
from django_app.payments.models import Payment, PaymentMethod, PaymentStatus

from .harness import LiveService

FEE_PATH = "flask_services/fee_service/app.py"
BARRIER_PATH = "flask_services/barrier_service/app.py"


# --------------------------------------------------------------------- Unit


class VehicleEntryServiceTests(TestCase):
    """Module 3: entry creates session, allocates slot, blocks duplicates."""

    def test_entry_creates_session_and_occupies_slot(self):
        ParkingSlot.objects.create(slot_number="A01")

        session = register_entry("kda 123x", "CAR")

        self.assertEqual(session.vehicle.plate_number, "KDA123X")
        self.assertEqual(session.slot.slot_number, "A01")
        self.assertEqual(session.status, SessionStatus.ACTIVE)
        session.slot.refresh_from_db()
        self.assertEqual(session.slot.status, SlotStatus.OCCUPIED)

    def test_duplicate_entry_rejected(self):
        ParkingSlot.objects.create(slot_number="A01")
        ParkingSlot.objects.create(slot_number="A02")

        register_entry("KDA 123X")
        with self.assertRaises(VehicleAlreadyParkedError):
            register_entry("kda123x")  # same plate, different case

    def test_full_lot_rejected(self):
        ParkingSlot.objects.create(slot_number="A01", status=SlotStatus.RESERVED)
        ParkingSlot.objects.create(slot_number="A02", status=SlotStatus.OCCUPIED)

        with self.assertRaises(ParkingLotFullError):
            register_entry("KDA 123X")

    def test_entry_records_attendant(self):
        ParkingSlot.objects.create(slot_number="A01")
        User = get_user_model()
        attendant = User.objects.create_user(username="att", password="x")

        session = register_entry("KDA 123X", user=attendant)

        self.assertEqual(session.registered_by, attendant)


class VehicleExitServiceTests(TestCase):
    """Module 4: duration, fee, payment, release - with fee client mocked."""

    def setUp(self):
        self.slot = ParkingSlot.objects.create(slot_number="A01")
        self.session = register_entry("KDA 123X")

    @patch("django_app.parking.services.exit.calculate_fee")
    def test_exit_completes_session_pays_and_releases(self, mock_fee):
        mock_fee.return_value = (180, Decimal("100"))
        entry = timezone.now() - timedelta(hours=3)
        ParkingSession.objects.filter(pk=self.session.pk).update(entry_time=entry)
        self.session.refresh_from_db()

        session, payment = register_exit(self.session.pk, PaymentMethod.MPESA)

        self.assertEqual(session.status, SessionStatus.COMPLETED)
        self.assertEqual(session.duration_minutes, 180)
        self.assertEqual(session.amount_paid, Decimal("100"))
        self.assertIsNotNone(session.exit_time)
        self.assertEqual(payment.payment_status, PaymentStatus.PAID)
        self.assertEqual(payment.amount, Decimal("100"))
        self.assertEqual(payment.payment_method, PaymentMethod.MPESA)
        self.slot.refresh_from_db()
        self.assertEqual(self.slot.status, SlotStatus.AVAILABLE)

    @patch("django_app.parking.services.exit.calculate_fee")
    def test_fee_service_failure_commits_nothing(self, mock_fee):
        mock_fee.side_effect = FeeServiceUnavailableError("down")

        with self.assertRaises(FeeServiceUnavailableError):
            register_exit(self.session.pk, PaymentMethod.CASH)

        self.session.refresh_from_db()
        self.assertEqual(self.session.status, SessionStatus.ACTIVE)
        self.assertIsNone(self.session.exit_time)
        self.assertEqual(Payment.objects.count(), 0)
        self.slot.refresh_from_db()
        self.assertEqual(self.slot.status, SlotStatus.OCCUPIED)

    def test_double_exit_rejected(self):
        with self.assertRaises(NoActiveSessionError):
            register_exit(99999, PaymentMethod.CASH)

    def test_search_by_plate_is_case_insensitive(self):
        found = get_active_session("  kda 123x ")
        self.assertIsNotNone(found)
        self.assertEqual(found.pk, self.session.pk)


# -------------------------------------------------------------- Integration


class DjangoToFlaskIntegrationTests(TestCase):
    """Real HTTP: Django service clients talking to live Flask services."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.fee = LiveService(FEE_PATH).start()
        cls.barrier = LiveService(BARRIER_PATH).start()
        cls._settings = override_settings(
            FEE_SERVICE_URL=cls.fee.base_url,
            BARRIER_SERVICE_URL=cls.barrier.base_url,
        )
        cls._settings.enable()

    @classmethod
    def tearDownClass(cls):
        cls._settings.disable()
        cls.fee.stop()
        cls.barrier.stop()
        super().tearDownClass()

    def test_fee_client_against_live_fee_service(self):
        from django_app.parking.services import clients

        entry = timezone.now() - timedelta(hours=3)
        duration, fee = clients.calculate_fee(entry, timezone.now())

        self.assertEqual(duration, 180)
        self.assertEqual(fee, Decimal("100"))

    def test_barrier_client_against_live_barrier_service(self):
        from django_app.parking.services import clients

        result = clients.open_barrier()

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["barrier"], "opened")

    def test_exit_flow_with_live_fee_service(self):
        ParkingSlot.objects.create(slot_number="A01")
        session = register_entry("KDA 123X")
        ParkingSession.objects.filter(pk=session.pk).update(
            entry_time=timezone.now() - timedelta(hours=2)
        )
        session.refresh_from_db()

        session, payment = register_exit(session.pk, PaymentMethod.CASH)

        self.assertEqual(payment.amount, Decimal("50"))  # <= 2h bracket
        self.assertEqual(session.duration_minutes, 120)

    def test_fee_service_down_raises_domain_error(self):
        from django_app.parking.services import clients

        self.fee.stop()
        try:
            with self.assertRaises(FeeServiceUnavailableError):
                clients.calculate_fee(timezone.now(), timezone.now())
        finally:
            self.fee = LiveService(FEE_PATH).start()  # restore for other tests


# ----------------------------------------------------------------- End to end


class VehicleFlowEndToEndTests(TestCase):
    """E2E: entry -> search -> fee -> payment -> slot released, via the views."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.fee = LiveService(FEE_PATH).start()
        cls.barrier = LiveService(BARRIER_PATH).start()
        cls._settings = override_settings(
            FEE_SERVICE_URL=cls.fee.base_url,
            BARRIER_SERVICE_URL=cls.barrier.base_url,
        )
        cls._settings.enable()

    @classmethod
    def tearDownClass(cls):
        cls._settings.disable()
        cls.fee.stop()
        cls.barrier.stop()
        super().tearDownClass()

    def setUp(self):
        for number in ("A01", "A02", "A03"):
            ParkingSlot.objects.create(slot_number=number)
        User = get_user_model()
        self.user = User.objects.create_user(
            username="attendant_e2e", password="pass"
        )
        self.client.force_login(self.user)

    def test_full_parking_lifecycle(self):
        # --- Module 3: entry ------------------------------------------------
        response = self.client.post(
            reverse("parking:entry"),
            {"plate_number": "kbz 987p", "vehicle_type": "SUV"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("parking:entry"))

        session = ParkingSession.objects.get()
        self.assertEqual(session.vehicle.plate_number, "KBZ987P")
        self.assertEqual(session.slot.slot_number, "A01")
        self.assertEqual(session.status, SessionStatus.ACTIVE)
        session.slot.refresh_from_db()
        self.assertEqual(session.slot.status, SlotStatus.OCCUPIED)

        messages = [m.message for m in get_messages(response.wsgi_request)]
        self.assertIn("Barrier OPEN.", " ".join(messages))

        # --- Module 4: search + fee quote -----------------------------------
        response = self.client.get(reverse("parking:exit"), {"plate": "kbz 987p"})
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.context["session"])
        self.assertIsNotNone(response.context["fee_quote"])
        duration, fee = response.context["fee_quote"]
        self.assertEqual(duration, 0)  # parked moments ago
        self.assertEqual(fee, Decimal("0"))  # <= 30 minutes is free

        # Backdate the entry so the fee bracket is non-trivial (3 hours = 100)
        ParkingSession.objects.filter(pk=session.pk).update(
            entry_time=timezone.now() - timedelta(hours=3)
        )

        response = self.client.get(reverse("parking:exit"), {"plate": "KBZ 987P"})
        self.assertEqual(response.context["fee_quote"], (180, Decimal("100")))

        # --- Module 4: payment + exit ---------------------------------------
        response = self.client.post(
            reverse("parking:exit"),
            {"session_id": session.pk, "payment_method": PaymentMethod.MPESA},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("parking:exit"))

        session.refresh_from_db()
        self.assertEqual(session.status, SessionStatus.COMPLETED)
        self.assertEqual(session.duration_minutes, 180)
        self.assertEqual(session.amount_paid, Decimal("100"))
        self.assertIsNotNone(session.exit_time)

        session.slot.refresh_from_db()
        self.assertEqual(session.slot.status, SlotStatus.AVAILABLE)

        payment = Payment.objects.get()
        self.assertEqual(payment.payment_status, PaymentStatus.PAID)
        self.assertEqual(payment.payment_method, PaymentMethod.MPESA)
        self.assertEqual(payment.amount, Decimal("100"))
        self.assertEqual(payment.received_by, self.user)

        messages = [m.message for m in get_messages(response.wsgi_request)]
        self.assertIn("Barrier OPEN.", " ".join(messages))

        # --- Dashboard reflects the day's activity --------------------------
        response = self.client.get(reverse("dashboard:home"))
        stats = response.context["stats"]
        self.assertEqual(stats["vehicles_today"], 1)
        self.assertEqual(stats["revenue_today"], Decimal("100"))
        self.assertEqual(stats["revenue_month"], Decimal("100"))
        self.assertEqual(stats["available"], 3)  # slot released again

    def test_entry_page_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("parking:entry"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)

    def test_vehicle_stays_listed_as_parked_until_exit(self):
        self.client.post(
            reverse("parking:entry"),
            {"plate_number": "KDA 123X", "vehicle_type": "CAR"},
        )
        Vehicle.objects.get(plate_number="KDA123X")

        response = self.client.get(reverse("parking:exit"))
        active = list(response.context["active_sessions"])
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].vehicle.plate_number, "KDA123X")
