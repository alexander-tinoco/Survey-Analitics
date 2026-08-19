"""Account models.

A custom user model is defined before the first migration ships, even though
it starts nearly identical to Django's. Swapping ``AUTH_USER_MODEL`` after a
database holds real users is one of the few genuinely painful migrations in
Django, and the cost of avoiding it now is a single class.
"""

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone

from .managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    """A person who uploads and analyzes survey data.

    Authentication is by email. Survey respondents are *not* users — they are
    rows in an uploaded dataset — so this model stays small on purpose.
    """

    email = models.EmailField("email address", unique=True)
    display_name = models.CharField(
        "display name",
        max_length=150,
        blank=True,
        help_text="Shown in the interface. Falls back to the email local part.",
    )
    is_staff = models.BooleanField(
        "staff status",
        default=False,
        help_text="Designates whether the user can log into the admin site.",
    )
    is_active = models.BooleanField(
        "active",
        default=True,
        help_text="Unselect this instead of deleting accounts, to preserve their datasets.",
    )
    date_joined = models.DateTimeField("date joined", default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        verbose_name = "user"
        verbose_name_plural = "users"
        ordering = ["-date_joined"]

    def __str__(self) -> str:
        return self.email

    @property
    def short_name(self) -> str:
        """A name for greetings, without forcing users to fill in a profile."""
        return self.display_name or self.email.split("@")[0]
