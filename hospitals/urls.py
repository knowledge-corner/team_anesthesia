from django.urls import path

from . import views

app_name = "hospitals"

urlpatterns = [
    path("", views.hospital_list, name="list"),
    path("search/", views.hospital_search, name="search"),
    path("add/", views.hospital_add, name="add"),
    path("directory/import/", views.directory_import, name="directory_import"),
    path("duplicates/", views.duplicates, name="duplicates"),
    path("merge/", views.merge, name="merge"),
    path("merge/<int:pk>/undo/", views.merge_undo, name="merge_undo"),
    path("<int:pk>/", views.hospital_detail, name="detail"),
    path("<int:pk>/edit/", views.hospital_edit, name="edit"),
]
