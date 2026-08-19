"""JWT-authenticated API endpoints for accounts."""

from rest_framework import generics, permissions
from rest_framework.request import Request
from rest_framework.response import Response

from .serializers import RegistrationSerializer, UserSerializer


class RegistrationView(generics.CreateAPIView):
    """Create an account.

    The only endpoint that has to be open, since a caller cannot authenticate
    before the account exists.
    """

    serializer_class = RegistrationSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request: Request, *args: object, **kwargs: object) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        # Answer with the public representation, not the write-only input.
        return Response(UserSerializer(user).data, status=201)


class CurrentUserView(generics.RetrieveAPIView):
    """Return the authenticated user, for clients verifying a stored token."""

    serializer_class = UserSerializer

    def get_object(self) -> object:
        return self.request.user
