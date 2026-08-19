"""Tests for the session-authenticated HTML pages."""

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

User = get_user_model()

PASSWORD = "correct-horse-battery"


@pytest.fixture
def user() -> object:
    return User.objects.create_user(
        email="alex@example.com", password=PASSWORD, display_name="Alex"
    )


@pytest.mark.django_db
class TestRegistrationPage:
    def test_page_renders_with_its_cat(self, client: Client) -> None:
        response = client.get(reverse("accounts:register"))

        assert response.status_code == 200
        assert "img/catRegister.png" in response.content.decode()

    def test_submitting_creates_the_account_and_logs_in(self, client: Client) -> None:
        """Asking someone to log in right after signing up is friction with no
        security benefit — the credentials were just proven.
        """
        response = client.post(
            reverse("accounts:register"),
            {
                "email": "new@example.com",
                "display_name": "New",
                "password": PASSWORD,
                "password_confirm": PASSWORD,
            },
        )

        assert response.status_code == 302
        assert User.objects.filter(email="new@example.com").exists()
        assert response.wsgi_request.user.is_authenticated

    def test_password_is_stored_hashed(self, client: Client) -> None:
        """The form bypasses ModelForm.save, which would store it in clear text."""
        client.post(
            reverse("accounts:register"),
            {
                "email": "new@example.com",
                "password": PASSWORD,
                "password_confirm": PASSWORD,
            },
        )

        created = User.objects.get(email="new@example.com")
        assert created.password != PASSWORD
        assert created.check_password(PASSWORD)

    def test_mismatched_confirmation_shows_an_error(self, client: Client) -> None:
        response = client.post(
            reverse("accounts:register"),
            {
                "email": "new@example.com",
                "password": PASSWORD,
                "password_confirm": "different",
            },
        )

        assert response.status_code == 200
        assert not User.objects.filter(email="new@example.com").exists()
        assert "do not match" in response.content.decode()


@pytest.mark.django_db
class TestLoginPage:
    def test_page_renders_with_its_cat(self, client: Client) -> None:
        response = client.get(reverse("accounts:login"))

        assert response.status_code == 200
        assert "img/catLogin.png" in response.content.decode()

    def test_valid_credentials_start_a_session(self, client: Client, user: object) -> None:
        response = client.post(
            reverse("accounts:login"),
            {"username": "alex@example.com", "password": PASSWORD},
        )

        assert response.status_code == 302
        assert response.wsgi_request.user.is_authenticated

    def test_error_message_does_not_reveal_whether_the_email_exists(
        self, client: Client, user: object
    ) -> None:
        """Distinguishing 'no such user' from 'wrong password' hands an
        attacker a way to enumerate registered accounts.
        """
        wrong_password = client.post(
            reverse("accounts:login"),
            {"username": "alex@example.com", "password": "wrong"},
        )
        unknown_email = client.post(
            reverse("accounts:login"),
            {"username": "nobody@example.com", "password": "wrong"},
        )

        message = "That email and password combination did not work."
        assert message in wrong_password.content.decode()
        assert message in unknown_email.content.decode()


@pytest.mark.django_db
class TestLogout:
    def test_logout_requires_post(self, client: Client, user: object) -> None:
        """A GET logout can be fired by a prefetch or an <img> tag."""
        client.force_login(user)

        response = client.get(reverse("accounts:logout"))

        assert response.status_code == 405

    def test_post_ends_the_session(self, client: Client, user: object) -> None:
        client.force_login(user)

        response = client.post(reverse("accounts:logout"))

        assert response.status_code == 302
        assert not response.wsgi_request.user.is_authenticated


@pytest.mark.django_db
class TestNavigation:
    def test_anonymous_visitors_see_the_sign_up_call(self, client: Client) -> None:
        content = client.get(reverse("home")).content.decode()

        assert reverse("accounts:register") in content
        assert reverse("accounts:login") in content

    def test_authenticated_users_see_their_name_and_a_logout_control(
        self, client: Client, user: object
    ) -> None:
        client.force_login(user)

        content = client.get(reverse("home")).content.decode()

        assert "Alex" in content
        assert reverse("accounts:logout") in content
