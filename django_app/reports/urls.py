"""Module 9 URLs: /reports/ and the CSV export."""

from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("", views.report_index, name="index"),
    path("export/", views.export_sessions, name="export"),
]
