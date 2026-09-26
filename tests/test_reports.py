"""Module 9 (Reports) + Module 8 (dashboard trend) tests."""

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from django_app.accounts.models import User, UserRole
from django_app.dashboard.services import trend_series
from django_app.parking.models import (
    ParkingSession,
    ParkingSlot,
    SessionStatus,
    SlotStatus,
    Vehicle,
)
from django_app.payments.models import Payment, PaymentMethod, PaymentStatus
from django_app.reports.services import (
    headline_figures,
    occupancy_breakdown,
    revenue_by_method,
    revenue_series,
)


class ReportAccessTests(TestCase):
    """RBAC on /reports/ and the CSV export (admin only)."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username="rep_admin", password="pw", role=UserRole.ADMIN
        )
        cls.attendant = User.objects.create_user(
            username="rep_att", password="pw", role=UserRole.ATTENDANT
        )

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse("reports:index"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)

    def test_attendant_forbidden(self):
        self.client.force_login(self.attendant)
        self.assertEqual(self.client.get(reverse("reports:index")).status_code, 403)
        self.assertEqual(self.client.get(reverse("reports:export")).status_code, 403)

    def test_admin_can_open_report(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("reports:index"))
        self.assertEqual(response.status_code, 200)
        for key in ("figures", "series", "methods", "occupancy", "sessions"):
            self.assertIn(key, response.context)
        self.assertEqual(len(response.context["series"]), 14)

    def test_dashboard_offers_trend_payload(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("dashboard:home"))
        self.assertEqual(response.status_code, 200)
        trend = response.context["trend"]
        self.assertEqual(len(trend), 7)
        for point in trend:
            for key in ("label", "entries", "exits", "revenue"):
                self.assertIn(key, point)
        self.assertContains(response, "trendChart")


class ReportFiguresTests(TestCase):
    """Aggregations must reflect what is actually in the database."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username="fig_admin", password="pw", role=UserRole.ADMIN
        )
        now = timezone.localtime()
        cls.slot = ParkingSlot.objects.create(
            slot_number="A01", status=SlotStatus.OCCUPIED
        )
        vehicle = Vehicle.objects.create(plate_number="KDA 123X", vehicle_type="CAR")
        cls.session = ParkingSession.objects.create(
            vehicle=vehicle,
            slot=cls.slot,
            entry_time=now - timedelta(hours=2),
            exit_time=now,
            duration_minutes=120,
            amount_paid=Decimal("50"),
            status=SessionStatus.COMPLETED,
            registered_by=cls.admin,
        )
        Payment.objects.create(
            parking_session=cls.session,
            amount=Decimal("50"),
            payment_method=PaymentMethod.MPESA,
            payment_status=PaymentStatus.PAID,
            paid_at=now,
            received_by=cls.admin,
        )

    def test_headline_figures(self):
        figures = headline_figures()
        self.assertEqual(figures["revenue_total"], 50.0)
        self.assertEqual(figures["revenue_today"], 50.0)
        self.assertEqual(figures["sessions_total"], 1)
        self.assertEqual(figures["sessions_completed"], 1)
        self.assertEqual(figures["sessions_active"], 0)
        self.assertEqual(figures["average_duration"], 120)

    def test_revenue_series_is_14_continuous_days_including_today(self):
        series = revenue_series(days=14)
        self.assertEqual(len(series), 14)
        self.assertEqual(series[-1]["date"], timezone.localdate().isoformat())
        self.assertEqual(sum(point["revenue"] for point in series), 50.0)
        self.assertEqual(series[-1]["payments"], 1)

    def test_revenue_by_method(self):
        methods = revenue_by_method()
        self.assertEqual(len(methods), 1)
        self.assertEqual(methods[0]["code"], "MPESA")
        self.assertEqual(methods[0]["total"], 50.0)
        self.assertEqual(methods[0]["count"], 1)

    def test_occupancy_breakdown_matches_slots(self):
        breakdown = occupancy_breakdown()
        self.assertEqual(sum(row["count"] for row in breakdown), 1)
        occupied = next(row for row in breakdown if row["code"] == "OCCUPIED")
        self.assertEqual(occupied["count"], 1)
        self.assertEqual(occupied["percent"], 100.0)


class SessionExportTests(TestCase):
    """CSV ledger download."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username="csv_admin", password="pw", role=UserRole.ADMIN
        )
        slot = ParkingSlot.objects.create(slot_number="B01")
        vehicle = Vehicle.objects.create(plate_number="KBZ 987P", vehicle_type="SUV")
        ParkingSession.objects.create(
            vehicle=vehicle,
            slot=slot,
            entry_time=timezone.localtime(),
            status=SessionStatus.ACTIVE,
            registered_by=cls.admin,
        )

    def test_export_returns_csv_with_every_session(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("reports:export"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("text/csv"))
        self.assertIn("attachment", response["Content-Disposition"])

        body = response.content.decode("utf-8-sig").strip().splitlines()
        self.assertIn("Plate,Vehicle type,Slot", body[0])
        self.assertEqual(len(body), ParkingSession.objects.count() + 1)
        self.assertIn("KBZ987P", body[1])


class TrendSeriesTests(TestCase):
    """7-day dashboard trend always returns a continuous, zero-filled series."""

    def test_series_is_continuous_even_with_no_data(self):
        series = trend_series(days=7)
        self.assertEqual(len(series), 7)
        self.assertTrue(all(point["entries"] == 0 for point in series))
        self.assertTrue(all(point["revenue"] == 0.0 for point in series))
        self.assertEqual(series[-1]["date"], timezone.localdate().isoformat())

    def test_series_counts_todays_activity(self):
        slot = ParkingSlot.objects.create(slot_number="C01")
        vehicle = Vehicle.objects.create(plate_number="KDC 111Q")
        ParkingSession.objects.create(
            vehicle=vehicle, slot=slot, entry_time=timezone.localtime()
        )
        series = trend_series(days=7)
        self.assertEqual(series[-1]["entries"], 1)
        self.assertEqual(series[-2]["entries"], 0)
