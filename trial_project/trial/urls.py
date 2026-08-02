from django.urls import path
from trial import views

urlpatterns = [
    path("", views.index, name="index"),
    path("host/setup/", views.host_setup, name="host_setup"),
    path("join/waiting/", views.join_waiting, name="join_waiting"),
]