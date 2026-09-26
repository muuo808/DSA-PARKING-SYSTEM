"""
Seed the database with demo parking slots.

Usage:  python manage.py seed_slots --count 10 --prefix A
Idempotent: existing slot numbers are skipped.
"""

from django.core.management.base import BaseCommand

from django_app.parking.models import ParkingSlot


class Command(BaseCommand):
    help = "Create demo parking slots (idempotent)."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--count", type=int, default=10, help="Number of slots (default 10)"
        )
        parser.add_argument(
            "--prefix", type=str, default="A", help="Slot prefix (default A)"
        )

    def handle(self, *args: object, **options: object) -> None:
        prefix: str = str(options["prefix"]).upper()
        count: int = int(options["count"])

        created = 0
        for index in range(1, count + 1):
            slot_number = f"{prefix}{index:02d}"
            _, was_created = ParkingSlot.objects.get_or_create(
                slot_number=slot_number
            )
            if was_created:
                created += 1

        total = ParkingSlot.objects.count()
        self.stdout.write(
            self.style.SUCCESS(
                f"Created {created} new slot(s). Total slots now: {total}."
            )
        )
