"""Forms for the session-authenticated HTML pages."""

from typing import Any

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.password_validation import validate_password

User = get_user_model()


class EmailLoginForm(AuthenticationForm):
    """Login form labelled for email, since that is the username field."""

    username = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={"autofocus": True, "autocomplete": "email"}),
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )

    # Shown when the credentials do not match. Deliberately vague: naming which
    # half was wrong tells an attacker which emails are registered.
    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "That email and password combination did not work.",
    }


class RegistrationForm(forms.ModelForm):
    """Create an account from the HTML registration page."""

    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    password_confirm = forms.CharField(
        label="Confirm password",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    class Meta:
        model = User
        fields = ["email", "display_name"]
        widgets = {
            "email": forms.EmailInput(attrs={"autofocus": True, "autocomplete": "email"}),
        }

    def clean_password(self) -> str:
        password = self.cleaned_data["password"]
        validate_password(password)
        return password

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean()
        password = cleaned.get("password")
        confirm = cleaned.get("password_confirm")

        if password and confirm and password != confirm:
            self.add_error("password_confirm", "The two password fields do not match.")

        return cleaned

    def save(self, commit: bool = True) -> Any:
        # Bypass ModelForm.save: it would assign the raw password to the field
        # instead of hashing it.
        return User.objects.create_user(
            email=self.cleaned_data["email"],
            password=self.cleaned_data["password"],
            display_name=self.cleaned_data.get("display_name", ""),
        )
