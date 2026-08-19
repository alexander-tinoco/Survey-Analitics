"""API endpoints for the descriptive layer."""

from django.shortcuts import get_object_or_404
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.surveys.models import Dataset

from .presenters import summary_to_dict
from .services import relational
from .services.descriptive import describe


class DescriptiveSummaryView(APIView):
    """Return the descriptive summary of a dataset as JSON."""

    def get(self, request: Request, pk: int) -> Response:
        dataset = get_object_or_404(Dataset, pk=pk, survey__owner=request.user)

        return Response(summary_to_dict(describe(dataset)))


class RelationalAnalysisView(APIView):
    """Return relational analysis, or the status of the job computing it.

    Answers immediately in every case. A caller polls this while the status
    is "running"; a request that blocked until the worker finished would tie
    up a connection for the length of the job.
    """

    def get(self, request: Request, pk: int) -> Response:
        dataset = get_object_or_404(Dataset, pk=pk, survey__owner=request.user)
        report = relational.request_analysis(dataset)

        return Response(
            {
                "status": str(report.status),
                "significant": len(report.significant),
                "associations": [relational.association_to_dict(a) for a in report.associations],
            },
            # 202 while work is in flight: the request was accepted but the
            # representation does not exist yet, which is what tells a client
            # to poll rather than to treat an empty list as the answer.
            status=200 if report.is_ready else 202,
        )
