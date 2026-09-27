"""User accounts and role management for AUTO-PARK."""

from django.contrib.auth.models import AbstractUser
from django.db import models


class UserRole(models.TextChoices):
    """Roles defined in Module 1: Admin and Attendant."""

    ADMIN = "ADMIN", "Admin"
    ATTENDANT = "ATTENDANT", "Attendant"


class User(AbstractUser):
    """
    AUTO-PARK user.

    Extends Django's AbstractUser so passwords are stored hashed (never
    plain text) while adding the role field required for role-based access
    control. Maps to the spec's ``users`` table.
    """

    role = models.CharField(
        max_length=20,
        choices=UserRole.choices,
        default=UserRole.ATTENDANT,
        help_text="Determines which actions this user may perform.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["username"]

    def __str__(self) -> str:
        return f"{self.username} ({self.get_role_display()})"

    @property
    def is_admin_role(self) -> bool:
        """True when the user may manage slots, users and reports.

        A superuser always outranks the stored role.
        """
        return bool(self.is_superuser or self.role == UserRole.ADMIN)

    @property
    def is_attendant_role(self) -> bool:
        """True when the user may register entry, exit and payments."""
        return bool(self.is_superuser or self.role == UserRole.ATTENDANT)
