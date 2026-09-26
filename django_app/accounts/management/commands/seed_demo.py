"""
Seed a fresh database with everything needed to sign in and demo the system.

    python manage.py seed_demo

Creates (idempotently - safe to run repeatedly):
  * demo users: admin (superuser + ADMIN role) and attendant (ATTENDANT)
  * 12 parking slots A01-A12

This is what makes a *fresh clone* usable: a new checkout has an empty
database (SQLite by default, or an empty Supabase schema), so without this
command there would be no account to sign in with.

Options:
    --slots N            how many slots to create (default 12)
    --prefix X           slot prefix (default A)
    --reset-passwords    force the demo passwords back onto existing users
"""

from django.core.management.base import BaseCommand

from django_app.accounts.models import User, UserRole
from django_app.parking.models import ParkingSlot

# Documented in README -> "Demo accounts". Only ever used for local demos.
DEMO_USERS = (
    {
        "username": "admin",
        "password": "fJvUta2d9b13",
        "role": UserRole.ADMIN,
        "superuser": True,
        "blurb": "everything: slots, users, /admin/, reports",
    },
    {
        "username": "attendant",
        "password": "attendant123",
        "role": UserRole.ATTENDANT,
        "superuser": False,
        "blurb": "entry, exit, payments, dashboard",
    },
)


class Command(BaseCommand):
    help = "Create demo users and parking slots so a fresh clone can sign in."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--slots", type=int, default=12, help="Number of slots (default 12)"
        )
        parser.add_argument(
            "--prefix", type=str, default="A", help="Slot prefix (default A)"
        )
        parser.add_argument(
            "--reset-passwords",
            action="store_true",
            help="Reset existing demo users to the documented passwords.",
        )

    def handle(self, *args: object, **options: object) -> None:
        reset = bool(options["reset_passwords"])

        # ---- users ------------------------------------------------------
        for spec in DEMO_USERS:
            user, created = User.objects.get_or_create(
                username=spec["username"],
                defaults={
                    "role": spec["role"],
                    "is_staff": spec["superuser"],
                    "is_superuser": spec["superuser"],
                },
            )
            # Keep role/flags consistent with the README even if the user
            # already existed (a fresh seed is idempotent).
            changed = []
            if user.role != spec["role"]:
                user.role = spec["role"]
                changed.append("role")
            if user.is_superuser != spec["superuser"]:
                user.is_superuser = spec["superuser"]
                user.is_staff = spec["superuser"]
                changed.append("superuser flag")
            if created or reset:
                user.set_password(spec["password"])
                changed.append("password")
            if changed:
                user.save()
            state = "created" if created else (
                f"updated ({', '.join(changed)})" if changed else "already present"
            )
            self.stdout.write(
                f"  user {spec['username']:<10} {state:<28} -> {spec['blurb']}"
            )

        # ---- slots ------------------------------------------------------
        prefix = str(options["prefix"]).upper()
        count = int(options["slots"])
        created_slots = 0
        for index in range(1, count + 1):
            _, was_created = ParkingSlot.objects.get_or_create(
                slot_number=f"{prefix}{index:02d}"
            )
            if was_created:
                created_slots += 1

        self.stdout.write(
            f"  slots {created_slots} new of {ParkingSlot.objects.count()} total "
            f"({prefix}01..{prefix}{count:02d})"
        )

        # ---- ready ------------------------------------------------------
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Demo data ready. Sign in with:"))
        table = (
            f"{'USER':<12}{'PASSWORD':<16}{'ROLE'}"
        )
        self.stdout.write(table)
        for spec in DEMO_USERS:
            role = "ADMIN (superuser)" if spec["superuser"] else "ATTENDANT"
            self.stdout.write(f"{spec['username']:<12}{spec['password']:<16}{role}")
        self.stdout.write("")
        self.stdout.write("Then start everything with ./run_dev.sh")
