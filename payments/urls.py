from django.urls import path

from . import views

app_name = "payments"

urlpatterns = [
    path("record/", views.record_payment, name="record"),
    path("record/case/<int:case_pk>/", views.record_payment, name="record_for_case"),
    path("bulk/", views.bulk_payment, name="bulk"),
    path("bulk/csv/", views.bulk_csv, name="bulk_csv"),
    path("bulk/upload/", views.bulk_upload, name="bulk_upload"),
    path("<int:pk>/edit/", views.edit_payment, name="edit"),
    path("case/<int:case_pk>/follow-up/", views.add_followup, name="followup_add"),
    path("case/<int:case_pk>/followed-up/", views.quick_followed_up, name="followup_quick"),
    path("case/<int:case_pk>/snooze/", views.snooze_followup, name="followup_snooze"),
]
