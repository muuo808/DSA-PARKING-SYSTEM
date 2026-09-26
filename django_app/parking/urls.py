from django.urls import path

from . import views

app_name = "parking"

urlpatterns = [
    path("", views.slot_list, name="slot_list"),
    path("slots/new/", views.slot_create, name="slot_create"),
    path(
        "slots/<int:pk>/status/",
        views.slot_update_status,
        name="slot_update_status",
    ),
    path("entry/", views.vehicle_entry, name="entry"),
    path("exit/", views.vehicle_exit, name="exit"),
]
