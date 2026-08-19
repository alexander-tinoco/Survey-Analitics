"""Export findings as files a reader can take away.

Findings are worth little if they only exist inside a browser tab: they end
up in a slide deck or a report, and the alternative to an export is somebody
retyping numbers by hand, which is where transcription errors come from.

CSV rather than a rendered document, because the destination is usually a
spreadsheet someone will keep working in. JSON alongside it, for anything
programmatic.
"""

import csv
from io import StringIO
from typing import Any

from apps.surveys.models import Dataset

CSV_COLUMNS = [
    "rank",
    "kind",
    "relevance",
    "finding",
    "questions",
    "evidence",
]


def findings_filename(dataset: Dataset, extension: str) -> str:
    """A filename that says which dataset and version it came from.

    Two exports of the same survey are otherwise indistinguishable in a
    downloads folder, which is exactly where they end up.
    """
    stem = dataset.survey.name.lower().replace(" ", "-")
    safe = "".join(char for char in stem if char.isalnum() or char in "-_")

    return f"{safe or 'survey'}-v{dataset.version}-findings.{extension}"


def findings_to_csv(insights: list[dict[str, Any]]) -> str:
    """Render findings as CSV.

    The evidence is flattened into one column rather than spread across a
    column per statistic: different kinds of finding carry different figures,
    and a sparse table with a mostly-empty column per measure is harder to
    read than the numbers written out.
    """
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_COLUMNS)

    for rank, insight in enumerate(insights, start=1):
        writer.writerow(
            [
                rank,
                insight["kind"],
                insight["relevance"],
                insight["text"],
                "; ".join(insight["questions"]),
                _flatten_evidence(insight["evidence"]),
            ]
        )

    return buffer.getvalue()


def _flatten_evidence(evidence: dict[str, Any]) -> str:
    """Render the figures behind a finding as readable key=value pairs."""
    return "; ".join(f"{key}={value}" for key, value in evidence.items())
