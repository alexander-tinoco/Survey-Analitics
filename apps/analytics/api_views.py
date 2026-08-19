"""API endpoints for the descriptive layer."""

from django.shortcuts import get_object_or_404
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.surveys.models import Dataset

from .presenters import summary_to_dict
from .services.descriptive import describe


class DescriptiveSummaryView(APIView):
    """Return the descriptive summary of a dataset as JSON."""

    def get(self, request: Request, pk: int) -> Response:
        dataset = get_object_or_404(Dataset, pk=pk, survey__owner=request.user)

        return Response(summary_to_dict(describe(dataset)))
