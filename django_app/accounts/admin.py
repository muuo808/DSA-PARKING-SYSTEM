"""Admin site configuration for user accounts."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """Admin dashboard: manage users and their roles."""

    list_display = ("username", "email", "role", "is_active", "created_at")
    list_filter = ("role", "is_active", "is_staff")
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("AUTO-PARK", {"fields": ("role",)}),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        ("AUTO-PARK", {"fields": ("role",)}),
    )
