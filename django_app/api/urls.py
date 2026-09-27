from django.urls import path

from . import views

app_name = "api"

# Read-only JSON resources (all except the descriptor need a staff session).
urlpatterns = [
    path("", views.api_root, name="root"),
    path("slots/", views.slots, name="slots"),
    path("vehicles/", views.vehicles, name="vehicles"),
    path("sessions/", views.sessions, name="sessions"),
    path("payments/", views.payments, name="payments"),
]
