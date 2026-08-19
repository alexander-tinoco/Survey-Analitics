"""Manager for the custom user model.

Django's default ``UserManager`` is built around a ``username`` field. This
model authenticates by email, so the creation helpers have to be replaced
rather than inherited unchanged.
"""

from typing import TYPE_CHECKING, Any

from django.contrib.auth.base_user import BaseUserManager

if TYPE_CHECKING:
    from .models import User


class UserManager(BaseUserManager["User"]):
    """Create users identified by email instead of username."""

    use_in_migrations = True

    def create_user(self, email: str, password: str | None = None, **extra: Any) -> "User":
        if not email:
            raise ValueError("Users must have an email address.")

        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)

        # Normalizing lowercases the domain part, so the uniqueness constraint
        # cannot be sidestepped with Alex@Example.com vs alex@example.com.
        user = self.model(email=self.normalize_email(email), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email: str, password: str | None = None, **extra: Any) -> "User":
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)

        if extra.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(email, password, **extra)
