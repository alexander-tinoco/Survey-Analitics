"""Session-authenticated HTML views."""

from django.contrib.auth import login
from django.contrib.auth.views import LoginView, LogoutView
from django.http import HttpResponse
from django.urls import reverse_lazy
from django.views.generic import CreateView

from .forms import EmailLoginForm, RegistrationForm


class CatLoginView(LoginView):
    """Log in and land on the dashboard."""

    template_name = "accounts/login.html"
    authentication_form = EmailLoginForm
    redirect_authenticated_user = True


class CatLogoutView(LogoutView):
    """Log out. POST-only, so a stray link or prefetch cannot end a session."""

    next_page = reverse_lazy("home")


class RegisterView(CreateView):
    """Create an account and sign the new user straight in."""

    form_class = RegistrationForm
    template_name = "accounts/register.html"
    success_url = reverse_lazy("home")

    def form_valid(self, form: RegistrationForm) -> HttpResponse:
        response = super().form_valid(form)
        # Registering and then being asked to log in is friction with no
        # security benefit: the credentials were just proven.
        login(self.request, self.object)
        return response
