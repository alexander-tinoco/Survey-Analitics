"""Respondent groups and question polarization.

Pure module (ADR 0001): DataFrames in, dataclasses out.

Clustering is the easiest place in this project to produce confident
nonsense. k-means always returns clusters — it will happily split pure noise
into four tidy groups and label them. Two guards are built in:

* **k is chosen, not assumed.** Silhouette score picks it, rather than a
  hardcoded "four segments" that the data never supported.
* **No structure is a valid answer.** When the best silhouette is too low,
  the result says the respondents do not fall into groups, instead of
  inventing some.

Polarization is separated from mere disagreement on purpose. A question where
answers spread evenly is *unsettled*; one where they pile up at both ends and
avoid the middle is *polarized*, and only the second describes a population
split into camps.
"""

import warnings
from dataclasses import dataclass, field
from enum import StrEnum

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.exceptions import ConvergenceWarning
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

# k-means is run for each candidate k, so the range stays small. Beyond six
# groups a survey report stops being readable anyway.
MIN_CLUSTERS = 2
MAX_CLUSTERS = 6

# Each group should hold enough people to describe. Below this, k-means is
# separating individuals rather than finding segments.
MIN_RESPONDENTS_PER_CLUSTER = 10

# Silhouette runs from -1 to 1. This is a floor, not the test: a partition
# below it is hopeless, but clearing it proves nothing on its own.
MIN_SILHOUETTE = 0.15

# The real test. One-hot encoding places respondents on the vertices of a
# hypercube, so k-means finds genuine *geometric* separation in answers that
# have no *population* structure at all — random categorical data reaches a
# silhouette around 0.30, twice the floor above.
#
# So the observed score is compared against the same data with each question
# shuffled independently. That destroys any relationship between questions
# while preserving every question's own distribution, which is exactly the
# null hypothesis: people answered each question the same way, but nobody
# answers as part of a group. Structure has to beat that, not merely exist.
NULL_PERMUTATIONS = 10

# Fixed so the same dataset always produces the same groups. A report whose
# segments change between two page loads is not a report.
RANDOM_STATE = 42

# How much separation is worth giving up for a simpler answer.
#
# Silhouette rises with k on one-hot data, because splitting a group always
# buys a little more geometric separation. Taking the maximum therefore
# oversegments: on a set with three real profiles it returned six, two of
# which were duplicates and two of which differed only by an unrelated
# question. Any k scoring within this margin of the best is treated as
# equally good, and the smallest of those wins — a reader can act on three
# profiles and cannot act on six that overlap.
PARSIMONY_TOLERANCE = 0.1

# An answer is characteristic of a group when it appears at least this many
# times more often than in the population as a whole.
CHARACTERISTIC_LIFT = 1.3
MIN_CHARACTERISTIC_SHARE = 0.25

# Share of answers sitting at the two ends of a scale before a question
# counts as polarized rather than merely spread out.
POLARIZED_EXTREME_SHARE = 0.6
# ...and the middle has to be comparatively empty, or a question everyone
# answers strongly in both directions is indistinguishable from one answered
# strongly in every direction.
POLARIZED_MAX_MIDDLE_SHARE = 0.25

# A single answer holding this share means the population agrees.
CONSENSUS_SHARE = 0.7

CLUSTERABLE_TYPES = frozenset({"categorical", "ordinal", "numeric"})
SCALE_TYPES = frozenset({"ordinal"})


class Verdict(StrEnum):
    """How a population answered one question."""

    CONSENSUS = "consensus"
    POLARIZED = "polarized"
    DIVIDED = "divided"
    MIXED = "mixed"


@dataclass(frozen=True)
class CharacteristicAnswer:
    """An answer that distinguishes a group from everyone else."""

    question: str
    answer: str
    group_share: float
    overall_share: float

    @property
    def lift(self) -> float:
        """How much more common this answer is inside the group."""
        if self.overall_share == 0:
            return 0.0
        return round(self.group_share / self.overall_share, 2)


@dataclass(frozen=True)
class RespondentGroup:
    """One cluster of respondents."""

    label: int
    size: int
    share: float
    characteristics: list[CharacteristicAnswer]

    @property
    def has_description(self) -> bool:
        """Whether anything actually distinguishes this group.

        A cluster with no characteristic answers exists in the encoded space
        but cannot be described to a reader, which makes it useless to report
        as a segment.
        """
        return bool(self.characteristics)


@dataclass(frozen=True)
class ClusterResult:
    """The outcome of looking for groups among respondents."""

    groups: list[RespondentGroup]
    silhouette: float
    respondents_clustered: int
    # Why clustering produced nothing, when it did.
    rejection_reason: str = ""

    @property
    def found_structure(self) -> bool:
        return bool(self.groups)


@dataclass(frozen=True)
class QuestionOpinion:
    """How divided a population is on one question."""

    question: str
    verdict: Verdict
    # Share held by the most common answer.
    modal_share: float
    # Share sitting at the two ends of the scale. Only meaningful for ordinal
    # questions, where the ends are opposites rather than just two options.
    extreme_share: float | None
    # Normalized entropy: 0 when everyone agrees, 1 when answers spread
    # evenly across every option.
    dispersion: float
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def is_notable(self) -> bool:
        """Whether this question is worth surfacing on its own."""
        return self.verdict in {Verdict.CONSENSUS, Verdict.POLARIZED}


def find_groups(
    frame: pd.DataFrame,
    question_types: dict[str, str],
    scales: dict[str, list[str]] | None = None,
) -> ClusterResult:
    """Group respondents by how similarly they answered.

    Returns an empty result with a reason rather than forcing groups onto
    data that has none.
    """
    usable = [
        column for column in frame.columns if question_types.get(str(column)) in CLUSTERABLE_TYPES
    ]

    if len(usable) < 2:
        return ClusterResult([], 0.0, 0, "Fewer than two questions can be compared.")

    scales = scales or {}
    encoded, kept_rows = _encode(frame[usable], question_types, scales)

    if len(encoded) < MIN_RESPONDENTS_PER_CLUSTER * MIN_CLUSTERS:
        return ClusterResult(
            [], 0.0, len(encoded), "Too few respondents answered enough questions."
        )

    best = _best_clustering(encoded, frame[usable], question_types, scales)
    if best is None:
        return ClusterResult(
            [],
            0.0,
            len(encoded),
            "Respondents do not separate into distinct groups. Any grouping "
            "found here is no clearer than one produced by shuffling the same "
            "answers at random, so their answers vary individually rather "
            "than falling into camps.",
        )

    labels, silhouette = best
    groups = _describe_groups(frame.loc[kept_rows], usable, labels)

    return ClusterResult(
        groups=groups,
        silhouette=round(float(silhouette), 4),
        respondents_clustered=len(encoded),
    )


def measure_opinion(
    frame: pd.DataFrame, question_types: dict[str, str], scales: dict[str, list[str]]
) -> list[QuestionOpinion]:
    """Classify every question by how divided the answers are."""
    return [
        opinion
        for column in frame.columns
        if question_types.get(str(column)) in {"categorical", "ordinal"}
        and (
            opinion := _measure_question(
                str(column),
                frame[column],
                question_types.get(str(column), "categorical"),
                scales.get(str(column), []),
            )
        )
        is not None
    ]


def _encode(
    frame: pd.DataFrame, question_types: dict[str, str], scales: dict[str, list[str]]
) -> tuple[np.ndarray, pd.Index]:
    """Turn mixed answer types into a numeric matrix k-means can read.

    Categorical answers become one-hot columns, because the distance between
    "Sales" and "Support" is not a number. Ordinal answers become their rank
    on their own scale, which is what keeps "Strongly agree" nearer to
    "Agree" than to "Disagree" — the single most useful piece of structure a
    survey carries. Numeric answers pass through.

    Everything is then standardized so a 0-100 question does not outweigh a
    1-5 one purely because its numbers are bigger.
    """
    pieces: list[pd.DataFrame] = []

    for column in frame.columns:
        answers = frame[column]
        question_type = question_types.get(str(column))

        if question_type == "categorical":
            pieces.append(_one_hot(answers, str(column)))
        elif question_type == "ordinal" and scales.get(str(column)):
            pieces.append(_rank_column(answers, scales[str(column)]).to_frame())
        else:
            numbers = pd.to_numeric(answers, errors="coerce")
            pieces.append(numbers.rename(str(column)).to_frame())

    weights: dict[str, float] = {}
    for piece in pieces:
        # A question's columns share its weight, so each question counts once
        # regardless of how many options it offered.
        share = 1.0 / np.sqrt(len(piece.columns)) if len(piece.columns) > 1 else 1.0
        for column in piece.columns:
            weights[str(column)] = share

    def weight_of(column: object) -> float:
        return weights.get(str(column), 1.0)

    combined = pd.concat(pieces, axis=1)
    # Respondents who skipped everything carry no information; the rest have
    # their gaps filled with the column mean so one blank does not drop them.
    combined = combined.dropna(how="all")
    combined = combined.fillna(combined.mean())
    combined = combined.dropna(axis=1, how="all").fillna(0.0)

    # StandardScaler first, so a 0-100 question does not outweigh a 1-5 one
    # by raw magnitude — then the per-question weights are reapplied, since
    # standardizing each column to unit variance would otherwise undo them.
    standardized = StandardScaler().fit_transform(combined)
    weights = np.array([weight_of(column) for column in combined.columns])

    return standardized * weights, combined.index


def _one_hot(answers: pd.Series, name: str) -> pd.DataFrame:
    """Expand a categorical question into one column per option.

    The weighting that keeps a many-option question from dominating is
    applied in :func:`_encode`, after standardization — doing it here would
    be undone by the scaler.
    """
    return pd.get_dummies(answers, prefix=name, dtype=float)


def _rank_column(answers: pd.Series, scale: list[str]) -> pd.Series:
    """Map ordinal answers onto their position in the scale.

    Text answers cannot be coerced to numbers directly — "Strongly agree" is
    not a float — and letting them fall through would flatten the column to a
    constant, discarding the ordering that the whole ordinal type exists to
    preserve.
    """
    positions = {point.lower(): index + 1 for index, point in enumerate(scale)}

    return (
        answers.map(lambda value: positions.get(str(value).lower()) if pd.notna(value) else None)
        .astype(float)
        .rename(answers.name)
    )


def _best_clustering(
    encoded: np.ndarray,
    frame: pd.DataFrame,
    question_types: dict[str, str],
    scales: dict[str, list[str]],
) -> tuple[np.ndarray, float] | None:
    """Try each plausible k and keep the clearest separation.

    Silhouette measures how much closer a respondent sits to their own group
    than to the next one. Choosing k this way is what stops the report from
    claiming four segments in data that only ever had two.
    """
    ceiling = min(MAX_CLUSTERS, len(encoded) // MIN_RESPONDENTS_PER_CLUSTER)
    if ceiling < MIN_CLUSTERS:
        return None

    scored: list[tuple[int, np.ndarray, float]] = []

    for k in range(MIN_CLUSTERS, ceiling + 1):
        labels = _fit(encoded, k)

        # Fewer distinct clusters than requested means the data ran out of
        # separable points; that k is not a real partition, and scoring it
        # would credit a k it never achieved.
        if labels is None:
            continue

        scored.append((k, labels, float(silhouette_score(encoded, labels))))

    best = _most_parsimonious(scored)

    if best is None or best[1] < MIN_SILHOUETTE:
        return None

    if best[1] <= _null_silhouette(frame, question_types, scales):
        return None

    return best


def _most_parsimonious(
    scored: list[tuple[int, np.ndarray, float]],
) -> tuple[np.ndarray, float] | None:
    """Pick the fewest groups that explain the data about as well as the most.

    Taking the highest silhouette outright oversegments, because splitting a
    group nearly always buys a little more separation. Anything within
    PARSIMONY_TOLERANCE of the top score is treated as an equally good
    account of the data, and among those the simplest one wins.
    """
    if not scored:
        return None

    ceiling = max(score for _, _, score in scored)
    acceptable = [
        (k, labels, score) for k, labels, score in scored if score >= ceiling - PARSIMONY_TOLERANCE
    ]

    _, labels, score = min(acceptable, key=lambda candidate: candidate[0])
    return labels, score


def _fit(encoded: np.ndarray, k: int) -> np.ndarray | None:
    """Cluster into exactly k groups, or report that it was not possible.

    Asking for more groups than there are distinct answer combinations is a
    normal part of the search — every k in the range is tried and the ones
    that do not fit are discarded on the next line. sklearn warns about it,
    which would fill the worker log with notices about a case already
    handled, so the warning is suppressed here and only here.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ConvergenceWarning)
        labels = KMeans(n_clusters=k, random_state=RANDOM_STATE, n_init=10).fit_predict(encoded)

    return labels if len(set(labels)) == k else None


def _null_silhouette(
    frame: pd.DataFrame, question_types: dict[str, str], scales: dict[str, list[str]]
) -> float:
    """Best silhouette reachable when the questions are unrelated.

    Each question's *answers* are shuffled, then the result is re-encoded.
    Shuffling the encoded matrix instead would be wrong: permuting one-hot
    columns independently produces rows like "Sales=1, Support=1", points no
    respondent could occupy, which scatter the space and make the null far
    easier to beat than it should be.

    Shuffling answers keeps every question's distribution intact and every
    row a real combination, while destroying any relationship between
    questions — precisely the null hypothesis. Whatever k-means scores there
    is separation the encoding creates on its own.

    The maximum across permutations is used rather than the mean: clearing
    the average would still let roughly half of all noise through.
    """
    generator = np.random.default_rng(RANDOM_STATE)
    best = 0.0

    for _ in range(NULL_PERMUTATIONS):
        shuffled = frame.apply(lambda column: generator.permutation(column.to_numpy()))
        encoded, _ = _encode(shuffled, question_types, scales)

        ceiling = min(MAX_CLUSTERS, len(encoded) // MIN_RESPONDENTS_PER_CLUSTER)
        for k in range(MIN_CLUSTERS, ceiling + 1):
            labels = _fit(encoded, k)
            if labels is None:
                continue
            best = max(best, float(silhouette_score(encoded, labels)))

    return best


def _describe_groups(
    frame: pd.DataFrame, questions: list[str], labels: np.ndarray
) -> list[RespondentGroup]:
    """Say what makes each group different from the population.

    A group described only as "cluster 2" tells a reader nothing. Comparing
    each group's answers against the overall distribution turns it into
    "the people who chose X and Y", which is the finding.
    """
    total = len(frame)
    groups: list[RespondentGroup] = []

    for label in sorted(set(labels)):
        members = frame[labels == label]

        groups.append(
            RespondentGroup(
                label=int(label),
                size=len(members),
                share=round(len(members) / total * 100, 1),
                characteristics=_characteristics_of(members, frame, questions),
            )
        )

    return sorted(groups, key=lambda group: -group.size)


def _characteristics_of(
    members: pd.DataFrame, everyone: pd.DataFrame, questions: list[str]
) -> list[CharacteristicAnswer]:
    """Find the answers over-represented in one group."""
    found: list[CharacteristicAnswer] = []

    for question in questions:
        group_answers = members[question].dropna()
        overall_answers = everyone[question].dropna()

        if group_answers.empty or overall_answers.empty:
            continue

        group_shares = group_answers.astype(str).value_counts(normalize=True)
        overall_shares = overall_answers.astype(str).value_counts(normalize=True)

        for answer, group_share in group_shares.items():
            overall_share = float(overall_shares.get(answer, 0.0))

            # Both thresholds matter: lift alone promotes a rare answer that
            # doubled from 2% to 4%, which describes nobody.
            if (
                group_share >= MIN_CHARACTERISTIC_SHARE
                and overall_share > 0
                and group_share / overall_share >= CHARACTERISTIC_LIFT
            ):
                found.append(
                    CharacteristicAnswer(
                        question=str(question),
                        answer=str(answer),
                        group_share=round(float(group_share) * 100, 1),
                        overall_share=round(overall_share * 100, 1),
                    )
                )

    return sorted(found, key=lambda c: -c.lift)


def _measure_question(
    question: str, answers: pd.Series, question_type: str, scale: list[str]
) -> QuestionOpinion | None:
    """Classify one question as consensus, polarized, divided or mixed."""
    answered = answers.dropna()
    if answered.empty:
        return None

    counts = answered.astype(str).value_counts()
    total = int(counts.sum())
    shares = counts / total

    modal_share = float(shares.iloc[0])
    dispersion = _normalized_entropy(shares.to_numpy())
    extreme_share = _extreme_share(counts, scale) if question_type in SCALE_TYPES else None

    return QuestionOpinion(
        question=question,
        verdict=_verdict(modal_share, extreme_share, counts, scale),
        modal_share=round(modal_share * 100, 1),
        extreme_share=None if extreme_share is None else round(extreme_share * 100, 1),
        dispersion=dispersion,
        counts={str(answer): int(count) for answer, count in counts.items()},
    )


def _verdict(
    modal_share: float, extreme_share: float | None, counts: pd.Series, scale: list[str]
) -> Verdict:
    """Decide what a distribution says about the population.

    Order matters: polarization is checked before consensus, because a
    question can have a large modal group and still be split into camps, and
    the split is the more interesting fact.
    """
    if (
        extreme_share is not None
        and extreme_share >= POLARIZED_EXTREME_SHARE
        and _middle_share(counts, scale) <= POLARIZED_MAX_MIDDLE_SHARE
    ):
        return Verdict.POLARIZED

    if modal_share >= CONSENSUS_SHARE:
        return Verdict.CONSENSUS

    if modal_share < 0.4:
        return Verdict.DIVIDED

    return Verdict.MIXED


def _extreme_share(counts: pd.Series, scale: list[str]) -> float | None:
    """Share of answers sitting at the two ends of a scale."""
    if len(scale) < 3:
        return None

    total = int(counts.sum())
    ends = {scale[0], scale[-1]}
    at_ends = sum(int(count) for answer, count in counts.items() if str(answer).lower() in ends)

    return at_ends / total if total else None


def _middle_share(counts: pd.Series, scale: list[str]) -> float:
    """Share of answers avoiding both ends of the scale."""
    if len(scale) < 3:
        return 1.0

    total = int(counts.sum())
    middle = set(scale[1:-1])
    inside = sum(int(count) for answer, count in counts.items() if str(answer).lower() in middle)

    return inside / total if total else 1.0


def _normalized_entropy(shares: np.ndarray) -> float:
    """How evenly answers are spread, on a 0-1 scale.

    Normalized by the number of options so a three-option question and a
    seven-option one can be compared: raw entropy grows with the number of
    choices regardless of how divided people are.
    """
    if len(shares) < 2:
        return 0.0

    entropy = -np.sum(shares * np.log(shares))
    return round(float(entropy / np.log(len(shares))), 4)
