"""API layer - /api/v1/ JSON resources (the descriptor advertised in README).

Two things must hold: the descriptor discovers only endpoints that really
exist (no 404s), and operational data (plates, payments) is never anonymous.
"""

from django.test import TestCase
from django.urls import reverse

from django_app.accounts.models import User, UserRole
from django_app.parking.models import (
    ParkingSession,
    ParkingSlot,
    SessionStatus,
    SlotStatus,
    Vehicle,
)
from django_app.payments.models import Payment, PaymentMethod, PaymentStatus


class ApiDescriptorTests(TestCase):
    """The descriptor is the contract - every path it lists must resolve."""

    def test_descriptor_lists_only_live_endpoints(self):
        payload = self.client.get(reverse("api:root")).json()
        self.assertEqual(payload["service"], "smartpark-api")
        for resource in payload["resources"]:
            response = self.client.get(resource["path"])
            # 200 for a staff session, 302 to login for anyone else - never 404.
            self.assertIn(response.status_code, (200, 302), resource["path"])


class ApiAccessTests(TestCase):
    """Plates and payments are staff data: anonymous requests are bounced."""

    ENDPOINTS = ("api:slots", "api:vehicles", "api:sessions", "api:payments")

    @classmethod
    def setUpTestData(cls):
        cls.attendant = User.objects.create_user(
            username="api_att", password="pw", role=UserRole.ATTENDANT
        )

    def test_anonymous_is_redirected_to_login(self):
        for name in self.ENDPOINTS:
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 302, name)
            self.assertIn(reverse("accounts:login"), response.url)

    def test_attendant_can_read_every_resource(self):
        self.client.force_login(self.attendant)
        for name in self.ENDPOINTS:
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)

    def test_endpoints_are_read_only(self):
        """POST must be rejected - this layer never writes state."""
        self.client.force_login(self.attendant)
        for name in self.ENDPOINTS:
            self.assertEqual(self.client.post(reverse(name)).status_code, 405, name)


class ApiPayloadTests(TestCase):
    """Shape of the data another client would actually consume."""

    @classmethod
    def setUpTestData(cls):
        cls.attendant = User.objects.create_user(
            username="api_pay", password="pw", role=UserRole.ATTENDANT
        )
        free = ParkingSlot.objects.create(slot_number="A01")
        taken = ParkingSlot.objects.create(
            slot_number="A02", status=SlotStatus.OCCUPIED
        )
        vehicle = Vehicle.objects.create(plate_number="KDA 123X")
        cls.session = ParkingSession.objects.create(
            vehicle=vehicle, slot=taken, status=SessionStatus.ACTIVE
        )
        Payment.objects.create(
            parking_session=cls.session,
            amount=50,
            payment_method=PaymentMethod.MPESA,
            payment_status=PaymentStatus.PAID,
        )
        cls.free_slot, cls.taken_slot = free, taken

    def test_slots_payload_reports_live_counts(self):
        self.client.force_login(self.attendant)
        payload = self.client.get(reverse("api:slots")).json()
        self.assertEqual(payload["count"], 2)
        self.assertEqual(payload["available"], 1)
        self.assertEqual(payload["occupied"], 1)
        self.assertEqual(
            [s["slot_number"] for s in payload["results"]], ["A01", "A02"]
        )

    def test_vehicles_payload_returns_normalised_plate(self):
        self.client.force_login(self.attendant)
        payload = self.client.get(reverse("api:vehicles")).json()
        self.assertEqual(payload["results"][0]["plate_number"], "KDA123X")

    def test_sessions_payload_carries_entry_and_fee_fields(self):
        self.client.force_login(self.attendant)
        payload = self.client.get(reverse("api:sessions")).json()
        row = payload["results"][0]
        self.assertEqual(row["plate_number"], "KDA123X")
        self.assertEqual(row["slot"], "A02")
        self.assertEqual(row["status"], SessionStatus.ACTIVE)
        self.assertIsNotNone(row["entry_time"])
        self.assertIsNone(row["exit_time"])

    def test_sessions_status_filter(self):
        """?status=ACTIVE narrows the feed; a bad value is ignored, not fatal."""
        self.client.force_login(self.attendant)
        active = self.client.get(reverse("api:sessions") + "?status=ACTIVE").json()
        self.assertEqual(active["count"], 1)
        completed = self.client.get(
            reverse("api:sessions") + "?status=COMPLETED"
        ).json()
        self.assertEqual(completed["count"], 0)
        nonsense = self.client.get(reverse("api:sessions") + "?status=WHATEVER").json()
        self.assertEqual(nonsense["count"], 1)

    def test_payments_payload_exposes_amount_and_method(self):
        self.client.force_login(self.attendant)
        payload = self.client.get(reverse("api:payments")).json()
        row = payload["results"][0]
        self.assertEqual(payload["count"], 1)
        # Money is serialised as a decimal *string* ("50.00"), never a float -
        # the same exactness rule as Decimal in the database (DESIGN.md (b) #7).
        self.assertEqual(row["amount"], "50.00")
        self.assertEqual(row["payment_method"], "MPESA")
        self.assertEqual(row["payment_status"], "PAID")
        self.assertEqual(row["plate_number"], "KDA123X")
