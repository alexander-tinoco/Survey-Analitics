"""API serializers for account operations."""

from typing import Any

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    """Public representation of a user. Never exposes the password hash."""

    class Meta:
        model = User
        fields = ["id", "email", "display_name", "date_joined"]
        read_only_fields = fields


class RegistrationSerializer(serializers.ModelSerializer):
    """Validate and create a new account.

    Password strength is checked with Django's configured validators rather
    than a local rule, so the API and the HTML form can never disagree about
    what counts as an acceptable password.
    """

    password = serializers.CharField(write_only=True, style={"input_type": "password"})
    password_confirm = serializers.CharField(write_only=True, style={"input_type": "password"})

    class Meta:
        model = User
        fields = ["email", "display_name", "password", "password_confirm"]

    def validate_password(self, value: str) -> str:
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError(
                {"password_confirm": "The two password fields do not match."}
            )
        return attrs

    def create(self, validated_data: dict[str, Any]) -> Any:
        validated_data.pop("password_confirm")
        # create_user hashes the password; Model.objects.create would store it
        # in clear text.
        return User.objects.create_user(**validated_data)
