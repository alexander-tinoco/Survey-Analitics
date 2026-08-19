"""Tests for the custom user model and its manager."""

import pytest
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.django_db
class TestUserCreation:
    def test_create_user_hashes_the_password(self) -> None:
        """A stored password must never be readable, even to us."""
        user = User.objects.create_user(email="alex@example.com", password="s3cure-pass!")

        assert user.password != "s3cure-pass!"
        assert user.check_password("s3cure-pass!")

    def test_email_is_normalized(self) -> None:
        """Domains are case-insensitive, so uniqueness must not be dodgeable."""
        user = User.objects.create_user(email="Alex@EXAMPLE.COM", password="s3cure-pass!")

        assert user.email == "Alex@example.com"

    def test_email_is_required(self) -> None:
        with pytest.raises(ValueError, match="email address"):
            User.objects.create_user(email="", password="s3cure-pass!")

    def test_email_must_be_unique(self) -> None:
        from django.db import IntegrityError

        User.objects.create_user(email="alex@example.com", password="s3cure-pass!")

        with pytest.raises(IntegrityError):
            User.objects.create_user(email="alex@example.com", password="other-pass!")

    def test_new_users_are_not_staff_or_superuser(self) -> None:
        """Privilege is opt-in. A default of False costs nothing to override."""
        user = User.objects.create_user(email="alex@example.com", password="s3cure-pass!")

        assert user.is_staff is False
        assert user.is_superuser is False
        assert user.is_active is True

    def test_create_superuser_sets_both_flags(self) -> None:
        admin = User.objects.create_superuser(email="root@example.com", password="s3cure-pass!")

        assert admin.is_staff is True
        assert admin.is_superuser is True

    @pytest.mark.parametrize(
        ("flag", "message"),
        [("is_staff", "is_staff=True"), ("is_superuser", "is_superuser=True")],
    )
    def test_create_superuser_rejects_contradictory_flags(self, flag: str, message: str) -> None:
        """A superuser without both flags is a silent half-privileged account."""
        with pytest.raises(ValueError, match=message):
            User.objects.create_superuser(
                email="root@example.com", password="s3cure-pass!", **{flag: False}
            )


@pytest.mark.django_db
class TestUserRepresentation:
    def test_str_is_the_email(self) -> None:
        user = User.objects.create_user(email="alex@example.com", password="s3cure-pass!")

        assert str(user) == "alex@example.com"

    def test_short_name_prefers_the_display_name(self) -> None:
        user = User.objects.create_user(
            email="alex@example.com", password="s3cure-pass!", display_name="Alex"
        )

        assert user.short_name == "Alex"

    def test_short_name_falls_back_to_the_email_local_part(self) -> None:
        """Greeting a user should not require them to fill in a profile."""
        user = User.objects.create_user(email="alex@example.com", password="s3cure-pass!")

        assert user.short_name == "alex"
