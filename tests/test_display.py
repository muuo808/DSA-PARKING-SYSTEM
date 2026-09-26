"""Module 10 - the public availability display at /display (UC-01).

This screen is the one part of the system a driver sees *before* entry, so
it must work without a login and must actually show which slots are free.
"""

from django.test import TestCase
from django.urls import reverse

from django_app.accounts.models import User, UserRole
from django_app.parking.models import ParkingSlot, SlotStatus


class DisplayAccessTests(TestCase):
    """The gate screen is public; every other page stays behind login."""

    @classmethod
    def setUpTestData(cls):
        cls.attendant = User.objects.create_user(
            username="disp_att", password="pw", role=UserRole.ATTENDANT
        )

    def test_anonymous_can_view_display(self):
        """No login wall - the driver has no account (core brief requirement)."""
        response = self.client.get(reverse("dashboard:display"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(getattr(response, "redirect_chain", None))

    def test_display_does_not_redirect_to_login(self):
        response = self.client.get(reverse("dashboard:display"))
        self.assertNotIn("login", response.url if response.status_code == 302 else "")

    def test_display_refreshes_itself(self):
        """Auto-refresh keeps the screen live without anyone touching it."""
        response = self.client.get(reverse("dashboard:display"))
        self.assertContains(response, 'http-equiv="refresh"')
        self.assertEqual(response.context["refresh_seconds"], 10)

    def test_dashboard_still_requires_login(self):
        """Contrast check: the public screen is the *only* open page."""
        response = self.client.get(reverse("dashboard:home"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)

    def test_attendant_can_view_display(self):
        self.client.force_login(self.attendant)
        self.assertEqual(
            self.client.get(reverse("dashboard:display")).status_code, 200
        )


class DisplaySlotMapTests(TestCase):
    """The map must show every slot with its state (not just aggregate counts)."""

    @classmethod
    def setUpTestData(cls):
        ParkingSlot.objects.create(slot_number="A01")  # defaults to AVAILABLE
        ParkingSlot.objects.create(
            slot_number="A02", status=SlotStatus.OCCUPIED
        )
        ParkingSlot.objects.create(
            slot_number="A03", status=SlotStatus.OUT_OF_SERVICE
        )

    def test_every_slot_is_rendered_with_its_state(self):
        response = self.client.get(reverse("dashboard:display"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "A01")
        self.assertContains(response, "A02")
        self.assertContains(response, "A03")
        self.assertContains(response, "FREE")     # available tile
        self.assertContains(response, "TAKEN")    # occupied tile
        self.assertContains(response, "CLOSED")   # out-of-service tile

    def test_slots_are_listed_in_slot_number_order(self):
        slots = list(self.client.get(reverse("dashboard:display")).context["slots"])
        self.assertEqual([s["slot_number"] for s in slots], ["A01", "A02", "A03"])

    def test_counts_match_the_map(self):
        response = self.client.get(reverse("dashboard:display"))
        stats = response.context["stats"]
        self.assertEqual(stats["total_slots"], 3)
        self.assertEqual(stats["available"], 1)
        self.assertEqual(stats["occupied"], 1)
        self.assertEqual(stats["out_of_service"], 1)

    def test_legend_present(self):
        """A driver must be able to decode the colours."""
        response = self.client.get(reverse("dashboard:display"))
        for label in ("Free", "Taken", "Reserved", "Closed"):
            self.assertContains(response, label)


class DisplayEmptyLotTests(TestCase):
    """A freshly seeded system shows the empty state, not a crash."""

    def test_empty_display_renders(self):
        response = self.client.get(reverse("dashboard:display"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No slots registered yet")
        self.assertEqual(response.context["stats"]["total_slots"], 0)
