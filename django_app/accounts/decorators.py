"""Role-based access control helpers (Module 1: user roles)."""

from collections.abc import Callable
from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden

from django_app.accounts.models import UserRole

FORBIDDEN_MESSAGE = "403 — your role does not permit this action."


def _is_admin(user: object) -> bool:
    """Admin role (or superuser, which always outranks roles)."""
    return bool(
        getattr(user, "is_authenticated", False)
        and (
            getattr(user, "is_superuser", False)
            or getattr(user, "role", None) == UserRole.ADMIN
        )
    )


def _is_attendant(user: object) -> bool:
    """Attendant role, admin role or superuser - all may operate the bay."""
    return bool(
        getattr(user, "is_authenticated", False)
        and getattr(user, "role", None) in {UserRole.ADMIN, UserRole.ATTENDANT}
    )


def _role_gate(test: Callable[[object], bool]) -> Callable:
    """
    Wrap a view with a role test.

    * anonymous          -> redirect to the login page (safe return path kept)
    * signed in, wrong role -> **403 with an explicit reason**

    The old behaviour (user_passes_test) bounced signed-in users back to the
    login page, which looked like a broken session instead of a permission
    problem - attendants reported it as "I cannot perform any action".
    """

    def decorator(view_func: Callable[..., HttpResponse]) -> Callable[..., HttpResponse]:
        @wraps(view_func)
        def wrapper(request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
            if test(request.user):
                return view_func(request, *args, **kwargs)
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            return HttpResponseForbidden(FORBIDDEN_MESSAGE)

        return wrapper

    return decorator


# Entry/exit/payment screens: any signed-in staff member.
attendant_required: Callable[[Callable[..., HttpResponse]], Callable[..., HttpResponse]]
attendant_required = _role_gate(_is_attendant)

# Slot management, user management, reports and revenue screens.
admin_required: Callable[[Callable[..., HttpResponse]], Callable[..., HttpResponse]]
admin_required = _role_gate(_is_admin)


def role_required(role: str) -> Callable:
    """
    Restrict a view to one specific role.

    Usage::

        @role_required(UserRole.ADMIN)
        def manage_users(request): ...
    """

    def test(user: object) -> bool:
        return bool(
            getattr(user, "is_authenticated", False)
            and (
                getattr(user, "is_superuser", False)
                or getattr(user, "role", None) == role
            )
        )

    return _role_gate(test)


def allow_roles(*roles: str) -> Callable:
    """Restrict a view to any of the given roles."""

    def test(user: object) -> bool:
        return bool(
            getattr(user, "is_authenticated", False)
            and (
                getattr(user, "is_superuser", False)
                or getattr(user, "role", None) in roles
            )
        )

    return _role_gate(test)


def require_role(role: str) -> Callable:
    """Decorator factory that raises 403-style redirect for wrong roles."""

    def decorator(view_func: Callable) -> Callable:
        @wraps(view_func)
        def wrapper(request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
            if not request.user.is_authenticated:
                from django.contrib.auth.views import redirect_to_login

                return redirect_to_login(request.get_full_path())
            if not (
                request.user.is_superuser or getattr(request.user, "role", None) == role
            ):
                return HttpResponseForbidden(FORBIDDEN_MESSAGE)
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator
