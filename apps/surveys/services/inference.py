"""Infer how each survey question should be treated statistically.

Pure module — DataFrame in, dataclasses out (ADR 0001).

Getting the type wrong is not a cosmetic mistake. A chi-square over free text
returns a number, and that number is noise; a five-point scale treated as free
text is dropped from analysis entirely. These heuristics are deliberately
conservative: when a column is ambiguous, it falls back to the type that
produces fewer false findings.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from enum import StrEnum

import pandas as pd

# Above this many distinct answers, a text column is prose rather than a set
# of options. Chosen from real surveys: even a long "select your department"
# list rarely passes 30 options, while free-text answers pass it immediately.
MAX_CATEGORICAL_DISTINCT = 30

# Even below the cap, a column whose answers are nearly all unique is prose.
MAX_CATEGORICAL_UNIQUE_RATIO = 0.5

# The ratio above is only meaningful once there are enough rows. In a 6-row
# sample, four options out of six is an ordinary categorical question, not
# prose — applying the ratio there would exclude small surveys from analysis
# entirely.
MIN_ROWS_FOR_UNIQUE_RATIO = 20

# Below this many distinct answers a column is a fixed set of options no
# matter how few rows it has.
ALWAYS_CATEGORICAL_DISTINCT = 10

# Selectable options are short by design — someone had to fit them in a radio
# button. Once the average answer runs longer than this, the column is prose
# even when few distinct values happen to appear, which is exactly the case a
# distinct-count rule alone gets wrong on a small sample.
MAX_OPTION_LENGTH = 25

# A rating scale is anchored: it starts at 0 or 1 and its top point is small.
# Distinct-count alone is not enough — five ages between 29 and 52 are also
# five distinct whole numbers, and calling them a scale would replace real
# ages with ranks 1 to 5.
MAX_ORDINAL_POINT = 10
MAX_ORDINAL_START = 1

# Real exports carry stray text in otherwise numeric columns — someone types
# "unknown" in an age field. Demanding every value parse would turn the whole
# column into free text and drop every valid number in it, so a minority of
# unparseable answers is tolerated and stored without a number.
#
# Set at four in five rather than nine in ten: on a 20-respondent survey a
# single odd answer is already 5%, and a stricter cut would discard small
# surveys for one typo while still admitting nothing genuinely mixed.
MIN_NUMERIC_RATIO = 0.8

# Ordered scales, lowest to highest. Matching one of these is what separates
# "Agree" (ordinal, differences are directional) from "Marketing"
# (categorical, differences are not).
#
# Spanish scales are listed alongside the English ones because the surveys
# this tool is built for are written in Spanish. Without them, "Muy de
# acuerdo" reads as an unordered option: the question still gets analyzed,
# but as a category, so nothing can tell that "De acuerdo" sits between
# "Neutral" and "Muy de acuerdo" — the ordering a rating scale exists to
# express is silently lost.
ORDINAL_SCALES: list[list[str]] = [
    ["strongly disagree", "disagree", "neutral", "agree", "strongly agree"],
    ["strongly disagree", "disagree", "neither", "agree", "strongly agree"],
    ["very dissatisfied", "dissatisfied", "neutral", "satisfied", "very satisfied"],
    ["very unsatisfied", "unsatisfied", "neutral", "satisfied", "very satisfied"],
    ["never", "rarely", "sometimes", "often", "always"],
    ["very poor", "poor", "average", "good", "excellent"],
    ["very low", "low", "medium", "high", "very high"],
    ["not at all", "slightly", "moderately", "very", "extremely"],
    # Spanish — agreement
    ["totalmente en desacuerdo", "en desacuerdo", "neutral", "de acuerdo", "totalmente de acuerdo"],
    ["muy en desacuerdo", "en desacuerdo", "neutral", "de acuerdo", "muy de acuerdo"],
    [
        "muy en desacuerdo",
        "en desacuerdo",
        "ni de acuerdo ni en desacuerdo",
        "de acuerdo",
        "muy de acuerdo",
    ],
    # Spanish — satisfaction
    ["muy insatisfecho", "insatisfecho", "neutral", "satisfecho", "muy satisfecho"],
    ["nada satisfecho", "poco satisfecho", "neutral", "satisfecho", "muy satisfecho"],
    # Spanish — frequency
    ["nunca", "casi nunca", "a veces", "casi siempre", "siempre"],
    ["nunca", "rara vez", "a veces", "frecuentemente", "siempre"],
    # Spanish — quality
    ["muy malo", "malo", "regular", "bueno", "excelente"],
    ["pesimo", "malo", "regular", "bueno", "excelente"],
    # Spanish — intensity
    ["muy bajo", "bajo", "medio", "alto", "muy alto"],
    ["nada", "poco", "algo", "bastante", "mucho"],
]

# Values that mean "no answer" regardless of the question.
MISSING_TOKENS = {
    "",
    "na",
    "n/a",
    "n.a.",
    "none",
    "null",
    "-",
    "--",
    "no answer",
    "prefer not to say",
    # Spanish equivalents, for the same reason the scales are bilingual.
    "ninguno",
    "ninguna",
    "sin respuesta",
    "no contesta",
    "no aplica",
    "prefiero no decir",
    "prefiero no contestar",
}


class InferredType(StrEnum):
    """Mirrors ``QuestionType`` without importing Django."""

    CATEGORICAL = "categorical"
    ORDINAL = "ordinal"
    NUMERIC = "numeric"
    FREE_TEXT = "free_text"


@dataclass(frozen=True)
class QuestionProfile:
    """What ingestion needs to know about one column."""

    position: int
    text: str
    type: InferredType
    distinct_values: int
    missing_count: int
    # Present only for ordinal questions: the answers in order, so a rating
    # can be turned into a rank for correlation.
    scale: list[str] = field(default_factory=list)


def normalize_answer(value: object) -> str:
    """Tidy an answer while keeping it readable.

    Trims and collapses internal whitespace, but preserves capitalization so
    the interface can show "Strongly agree" rather than "strongly agree".
    Use :func:`canonical_answer` to decide whether two answers are the same.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def canonical_answer(value: object) -> str:
    """Reduce an answer to the form used for grouping and counting.

    Case and accents are dropped here and only here. "Yes", "yes" and " Yes "
    are one answer; counting them as three splits a bar chart that should
    have had one bar, and inflates the distinct count that drives type
    inference.

    Accents are folded because survey exports are inconsistent about them —
    "Muy satisfecho" and "Muy satisfecho" typed without the accent are the
    same answer, and a scale match must not fail over a missing tilde.
    """
    stripped = unicodedata.normalize("NFKD", normalize_answer(value))
    return "".join(char for char in stripped if not unicodedata.combining(char)).lower()


def is_missing(value: object) -> bool:
    """Whether an answer represents no response."""
    return canonical_answer(value) in MISSING_TOKENS


def profile_frame(frame: pd.DataFrame) -> list[QuestionProfile]:
    """Infer a profile for every column, left to right."""
    return [
        _profile_column(position, str(column), frame[column])
        for position, column in enumerate(frame.columns)
    ]


def _profile_column(position: int, text: str, column: pd.Series) -> QuestionProfile:
    answered = column[~column.map(is_missing)]
    missing_count = len(column) - len(answered)
    distinct = int(answered.map(canonical_answer).nunique())

    inferred, scale = _infer_type(answered, distinct)

    return QuestionProfile(
        position=position,
        text=text,
        type=inferred,
        distinct_values=distinct,
        missing_count=missing_count,
        scale=scale,
    )


def _infer_type(answered: pd.Series, distinct: int) -> tuple[InferredType, list[str]]:
    """Decide a column's type from its answered values."""
    if answered.empty:
        # Nothing to go on. Free text is the safe default: it is excluded from
        # statistical tests rather than feeding them an empty distribution.
        return InferredType.FREE_TEXT, []

    numeric = pd.to_numeric(answered, errors="coerce")
    if numeric.notna().mean() >= MIN_NUMERIC_RATIO:
        return _infer_numeric_type(numeric.dropna(), distinct)

    values = answered.map(normalize_answer)
    matched_scale = _match_ordinal_scale(values)
    if matched_scale:
        return InferredType.ORDINAL, matched_scale

    if _is_categorical(values, distinct):
        return InferredType.CATEGORICAL, []

    return InferredType.FREE_TEXT, []


def _is_categorical(values: pd.Series, distinct: int) -> bool:
    """Whether a text column is a fixed set of options rather than prose.

    Two signals, because either one alone misreads a common case: answer
    length catches long sentences that happen to be few, and the distinct
    count catches short answers that happen to be many.
    """
    if distinct > MAX_CATEGORICAL_DISTINCT:
        return False

    if values.str.len().mean() > MAX_OPTION_LENGTH:
        return False

    if distinct <= ALWAYS_CATEGORICAL_DISTINCT:
        return True

    if len(values) < MIN_ROWS_FOR_UNIQUE_RATIO:
        return True

    return distinct / len(values) <= MAX_CATEGORICAL_UNIQUE_RATIO


def _infer_numeric_type(numeric: pd.Series, distinct: int) -> tuple[InferredType, list[str]]:
    """Separate a rating scale from a measurement.

    A 1-5 satisfaction rating and an age in years are both whole numbers, but
    only one of them has a meaningful mean. The scale is identified by where
    it sits, not by how many values it has: ratings are anchored at 0 or 1 and
    top out in single digits, while measurements start wherever the population
    happens to start.
    """
    del distinct  # the range decides, not the count

    if not bool((numeric == numeric.round()).all()):
        return InferredType.NUMERIC, []

    low, high = numeric.min(), numeric.max()
    if low > MAX_ORDINAL_START or high > MAX_ORDINAL_POINT or low < 0:
        return InferredType.NUMERIC, []

    ordered = sorted(numeric.unique())
    return InferredType.ORDINAL, [str(int(v)) for v in ordered]


def _match_ordinal_scale(values: pd.Series) -> list[str]:
    """Return the known scale a column's answers belong to, if any.

    Requires every answer to appear in one scale. A single unexpected option
    means the column is not that scale, and guessing an order for it would
    invent structure the data does not have.
    """
    present = {canonical_answer(v) for v in values.unique() if v}
    if not present:
        return []

    for scale in ORDINAL_SCALES:
        if present <= set(scale):
            # Keep only the points actually used, in the scale's order.
            return [point for point in scale if point in present]

    return []
