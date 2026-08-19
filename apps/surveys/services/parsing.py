"""Read an uploaded survey export into a DataFrame.

Pure module: it takes bytes and returns a DataFrame. No Django, no database,
no filesystem. That keeps every parsing edge case testable from a literal in
the test file (ADR 0001).
"""

import io
from dataclasses import dataclass

import pandas as pd

MAX_COLUMNS = 500
MAX_ROWS = 100_000

# The delimiters real survey exports use. Ordered by how common they are, so
# a tie goes to the likelier one.
DELIMITERS = (",", ";", "\t", "|")


class ParseError(Exception):
    """The file cannot be read as survey data.

    Carries a message meant for the person who uploaded the file, not a stack
    trace: they can fix a stray delimiter, they cannot fix a traceback.
    """


@dataclass(frozen=True)
class ParsedFile:
    """A successfully read export."""

    frame: pd.DataFrame
    filename: str

    @property
    def respondent_count(self) -> int:
        return len(self.frame)

    @property
    def question_count(self) -> int:
        return len(self.frame.columns)


def parse_upload(content: bytes, filename: str) -> ParsedFile:
    """Read ``content`` into a DataFrame, choosing the reader by extension."""
    if not content:
        raise ParseError("The file is empty.")

    lowered = filename.lower()
    if lowered.endswith(".csv"):
        frame = _read_csv(content)
    elif lowered.endswith((".xlsx", ".xls")):
        frame = _read_excel(content)
    else:
        raise ParseError("Only .csv, .xlsx and .xls files are supported.")

    return ParsedFile(frame=_clean(frame), filename=filename)


def _read_csv(content: bytes) -> pd.DataFrame:
    """Read CSV using the delimiter its header row implies.

    The delimiter is decided first, from the header alone, and the file is
    then read exactly once with it. Trying every candidate and keeping
    whichever parsed looks robust but hides real problems: a file with ragged
    rows fails on its true delimiter and then "succeeds" on another that
    happens to appear nowhere, yielding one column and no error at all.
    """
    text = _decode(content)

    try:
        return pd.read_csv(io.StringIO(text), sep=_detect_delimiter(text))
    except pd.errors.EmptyDataError as exc:
        raise ParseError("The file has no readable rows.") from exc
    except pd.errors.ParserError as exc:
        raise ParseError(
            "The rows do not have a consistent number of columns. "
            "Check for an unescaped quote or delimiter."
        ) from exc


def _detect_delimiter(text: str) -> str:
    """Pick the delimiter that appears most often in the header row.

    Counting on the header rather than the whole file keeps commas inside
    answers from outvoting the real separator. When nothing appears, any
    candidate reads the file as a single column, so the default is harmless.

    pandas can sniff this itself with ``sep=None``, but its sniffer considers
    any character: given a one-column file it split the header "Rating" on
    the letter t.
    """
    header = text.splitlines()[0] if text.splitlines() else ""
    counts = {delimiter: header.count(delimiter) for delimiter in DELIMITERS}
    best = max(DELIMITERS, key=lambda d: counts[d])

    return best if counts[best] else ","


def _decode(content: bytes) -> str:
    """Decode file bytes to text.

    UTF-8 is tried first and its BOM stripped, since that is what current
    spreadsheet software writes. latin-1 is the fallback because it maps every
    possible byte: it may render an unusual character oddly, but it never
    refuses a file, and the structural checks downstream catch anything that
    is genuinely not survey data.
    """
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return content.decode("latin-1")


def _read_excel(content: bytes) -> pd.DataFrame:
    """Read the first sheet of a workbook."""
    try:
        return pd.read_excel(io.BytesIO(content), sheet_name=0)
    except Exception as exc:
        raise ParseError(
            "The file could not be read as a spreadsheet. Is it a real .xlsx workbook?"
        ) from exc


def _clean(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize the shape of a freshly read export.

    Survey exports routinely carry blank trailing columns, an unnamed index
    column, and rows that are entirely empty. Dropping them here means every
    downstream stage can assume the frame is rectangular and meaningful.
    """
    frame = frame.dropna(axis=1, how="all")
    frame = frame.dropna(axis=0, how="all")
    frame = frame.loc[:, [not str(c).startswith("Unnamed:") for c in frame.columns]]
    frame.columns = [str(c).strip() for c in frame.columns]

    if frame.empty or len(frame.columns) == 0:
        raise ParseError("The file has no data rows.")
    if len(frame.columns) > MAX_COLUMNS:
        raise ParseError(f"The file has more than {MAX_COLUMNS} columns.")
    if len(frame) > MAX_ROWS:
        raise ParseError(f"The file has more than {MAX_ROWS:,} rows.")
    _reject_duplicate_headers(frame)

    return frame.reset_index(drop=True)


def _reject_duplicate_headers(frame: pd.DataFrame) -> None:
    """Refuse a file whose header row repeats a question title.

    pandas silently disambiguates duplicates before we ever see the frame,
    turning a repeated "Age" into "Age" and "Age.1". So the check cannot look
    for identical names — it has to look for that rename. Left alone, the user
    would see a question they never wrote, and every result mentioning it
    would be ambiguous.
    """
    names = [str(c) for c in frame.columns]
    originals = set(names)

    for name in names:
        base, separator, suffix = name.rpartition(".")
        if separator and suffix.isdigit() and base in originals:
            raise ParseError(
                f"The header {base!r} appears more than once. Question titles must be unique."
            )
