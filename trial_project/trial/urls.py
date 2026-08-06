from django.urls import path
from trial import views

urlpatterns = [
    path("", views.index, name="index"),
    path("enter", views.enter, name="enter"),
    path("host/setup", views.host_setup, name="host_setup"),
    path("host/setup/start", views.host_setup_start, name="host_setup_start"),
    path("host/setup/game", views.host_setup_game, name="host_setup_game"),
    path("host/setup/game/start", views.host_setup_game_start, name="host_setup_game_start"),
    path("join/waiting", views.join_waiting, name="join_waiting"),
    path("role-reveal", views.role_reveal, name="role_reveal"),
    path("trial", views.trial, name="trial"),
    path("verdict", views.verdict, name="verdict"),
]
