"""Tests for the JWT authentication API."""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

User = get_user_model()

PASSWORD = "correct-horse-battery"


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def user() -> object:
    return User.objects.create_user(email="alex@example.com", password=PASSWORD)


@pytest.mark.django_db
class TestRegistration:
    def test_registering_creates_an_account(self, api: APIClient) -> None:
        response = api.post(
            reverse("accounts_api:register"),
            {
                "email": "new@example.com",
                "display_name": "New",
                "password": PASSWORD,
                "password_confirm": PASSWORD,
            },
            format="json",
        )

        assert response.status_code == 201
        assert User.objects.filter(email="new@example.com").exists()

    def test_response_never_contains_the_password(self, api: APIClient) -> None:
        """A password echoed back lands in logs, proxies, and browser history."""
        response = api.post(
            reverse("accounts_api:register"),
            {
                "email": "new@example.com",
                "password": PASSWORD,
                "password_confirm": PASSWORD,
            },
            format="json",
        )

        assert "password" not in response.json()

    def test_mismatched_confirmation_is_rejected(self, api: APIClient) -> None:
        response = api.post(
            reverse("accounts_api:register"),
            {
                "email": "new@example.com",
                "password": PASSWORD,
                "password_confirm": "something-else",
            },
            format="json",
        )

        assert response.status_code == 400
        assert "password_confirm" in response.json()

    def test_weak_password_is_rejected(self, api: APIClient) -> None:
        """Django's validators apply here, not a weaker local rule."""
        response = api.post(
            reverse("accounts_api:register"),
            {"email": "new@example.com", "password": "123", "password_confirm": "123"},
            format="json",
        )

        assert response.status_code == 400
        assert "password" in response.json()

    def test_duplicate_email_is_rejected(self, api: APIClient, user: object) -> None:
        response = api.post(
            reverse("accounts_api:register"),
            {
                "email": "alex@example.com",
                "password": PASSWORD,
                "password_confirm": PASSWORD,
            },
            format="json",
        )

        assert response.status_code == 400


@pytest.mark.django_db
class TestTokenFlow:
    def test_valid_credentials_return_a_token_pair(self, api: APIClient, user: object) -> None:
        response = api.post(
            reverse("accounts_api:login"),
            {"email": "alex@example.com", "password": PASSWORD},
            format="json",
        )

        assert response.status_code == 200
        assert "access" in response.json()
        assert "refresh" in response.json()

    def test_wrong_password_is_refused(self, api: APIClient, user: object) -> None:
        response = api.post(
            reverse("accounts_api:login"),
            {"email": "alex@example.com", "password": "wrong"},
            format="json",
        )

        assert response.status_code == 401

    def test_refresh_token_yields_a_new_access_token(self, api: APIClient, user: object) -> None:
        tokens = api.post(
            reverse("accounts_api:login"),
            {"email": "alex@example.com", "password": PASSWORD},
            format="json",
        ).json()

        response = api.post(
            reverse("accounts_api:refresh"),
            {"refresh": tokens["refresh"]},
            format="json",
        )

        assert response.status_code == 200
        assert "access" in response.json()

    def test_rotated_refresh_token_cannot_be_replayed(self, api: APIClient, user: object) -> None:
        """With rotation and blacklisting on, a stolen refresh token dies on
        first use by its rightful owner instead of granting a parallel session.
        """
        tokens = api.post(
            reverse("accounts_api:login"),
            {"email": "alex@example.com", "password": PASSWORD},
            format="json",
        ).json()
        original_refresh = tokens["refresh"]

        api.post(reverse("accounts_api:refresh"), {"refresh": original_refresh}, format="json")

        replay = api.post(
            reverse("accounts_api:refresh"), {"refresh": original_refresh}, format="json"
        )

        assert replay.status_code == 401


@pytest.mark.django_db
class TestProtectedEndpoints:
    def test_me_requires_authentication(self, api: APIClient) -> None:
        response = api.get(reverse("accounts_api:me"))

        assert response.status_code == 401

    def test_me_returns_the_authenticated_user(self, api: APIClient, user: object) -> None:
        tokens = api.post(
            reverse("accounts_api:login"),
            {"email": "alex@example.com", "password": PASSWORD},
            format="json",
        ).json()
        api.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

        response = api.get(reverse("accounts_api:me"))

        assert response.status_code == 200
        assert response.json()["email"] == "alex@example.com"
