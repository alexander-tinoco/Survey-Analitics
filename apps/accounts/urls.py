"""HTML routes for accounts."""

from django.urls import path

from .views import CatLoginView, CatLogoutView, RegisterView

app_name = "accounts"

urlpatterns = [
    path("login/", CatLoginView.as_view(), name="login"),
    path("logout/", CatLogoutView.as_view(), name="logout"),
    path("register/", RegisterView.as_view(), name="register"),
]
