"""Turn statistical results into sentences a non-statistician can read.

Pure module (ADR 0001): dataclasses in, dataclasses out.

This is the layer the product exists for. Everything before it produces
numbers that a reader has to interpret; this one states what the numbers
mean. Two rules keep that from becoming embellishment:

* **Every sentence carries its evidence.** An insight holds the figures it
  was built from, and a test asserts the numbers in the text match them. A
  claim the reader cannot check is a claim they should not trust.
* **Nothing unreliable is narrated.** An association that failed its
  assumptions, a cluster that did not beat chance, a question answered by
  eleven people — these produce no sentence at all. Silence is a correct
  output; a confident sentence about noise is not.
"""

from dataclasses import dataclass, field
from enum import StrEnum

from .descriptive import DatasetSummary, QuestionDistribution
from .patterns import ClusterResult, QuestionOpinion, RespondentGroup, Verdict
from .relational import Association

# Below this share of respondents, a finding describes too few people to be
# worth a sentence of its own.
MIN_COVERAGE = 0.1

# A row percentage has to clear the overall rate by this much before it is
# worth saying. "52% of X also chose Y, against 50% overall" is not a finding.
MIN_LIFT = 1.25

# Cap on how many sentences are produced. A page of forty insights is a page
# nobody reads, and the ranking exists precisely so the top few are the ones
# that matter.
MAX_INSIGHTS = 12


class InsightKind(StrEnum):
    """Which layer produced a sentence, for grouping in the interface."""

    RELATIONSHIP = "relationship"
    PROFILE = "profile"
    CONSENSUS = "consensus"
    POLARIZATION = "polarization"
    PARTICIPATION = "participation"
    DISTRIBUTION = "distribution"


@dataclass(frozen=True)
class Insight:
    """One readable finding, with the figures behind it."""

    text: str
    kind: InsightKind
    # 0-1. Drives ordering, so the strongest finding is read first.
    relevance: float
    questions: list[str]
    evidence: dict[str, float | str] = field(default_factory=dict)


def generate(
    summary: DatasetSummary,
    associations: list[Association],
    clusters: ClusterResult | None,
    opinions: list[QuestionOpinion],
) -> list[Insight]:
    """Produce the readable findings for a dataset, strongest first.

    Takes the output of all three layers rather than recomputing anything:
    a sentence that disagreed with the table beside it would be worse than
    no sentence.
    """
    found = [
        *_relationship_insights(associations, summary.respondents),
        *_profile_insights(clusters),
        *_opinion_insights(opinions, summary.respondents),
        *_participation_insights(summary),
        *_distribution_insights(summary),
    ]

    return sorted(found, key=lambda insight: -insight.relevance)[:MAX_INSIGHTS]


def _relationship_insights(associations: list[Association], respondents: int) -> list[Insight]:
    """Narrate the strongest cell of each significant association.

    Not the whole table: the finding a reader can act on is one combination
    that occurs far more often than it should, and a sentence per table cell
    would bury it.
    """
    insights: list[Insight] = []

    for association in associations:
        # Unreliable associations already report is_significant as False, so
        # this single check covers assumptions and correction together.
        if not association.is_significant:
            continue

        cell = _strongest_cell(association)
        if cell is None:
            continue

        row_answer, column_answer, row_share, overall_share, row_total = cell

        insights.append(
            Insight(
                text=(
                    f"{row_share}% of respondents who answered "
                    f"“{row_answer}” to “{association.row_question}” also answered "
                    f"“{column_answer}” to “{association.column_question}” — "
                    f"against {overall_share}% across everyone."
                ),
                kind=InsightKind.RELATIONSHIP,
                relevance=_relationship_relevance(association, row_total, respondents),
                questions=[association.row_question, association.column_question],
                evidence={
                    "row_answer": row_answer,
                    "column_answer": column_answer,
                    "row_share": row_share,
                    "overall_share": overall_share,
                    "respondents_in_row": row_total,
                    "cramers_v": association.cramers_v,
                    "adjusted_p_value": association.adjusted_p_value or association.p_value,
                },
            )
        )

    return insights


def _strongest_cell(
    association: Association,
) -> tuple[str, str, float, float, int] | None:
    """Find the combination that most exceeds what independence predicts.

    Row share against overall share, not raw count: the largest cell in a
    table is usually just the largest row, which says nothing about a
    relationship.
    """
    table = association.table
    total = table.total
    if total == 0:
        return None

    column_totals = table.column_totals
    best: tuple[str, str, float, float, int] | None = None
    best_lift = MIN_LIFT

    for row_index, row_counts in enumerate(table.counts):
        row_total = table.row_totals[row_index]
        if row_total == 0 or row_total / total < MIN_COVERAGE:
            continue

        for column_index, count in enumerate(row_counts):
            overall_share = column_totals[column_index] / total
            if overall_share == 0:
                continue

            row_share = count / row_total
            lift = row_share / overall_share

            if lift > best_lift:
                best_lift = lift
                best = (
                    table.row_labels[row_index],
                    table.column_labels[column_index],
                    round(row_share * 100, 1),
                    round(overall_share * 100, 1),
                    row_total,
                )

    return best


def _relationship_relevance(association: Association, row_total: int, respondents: int) -> float:
    """Rank a relationship by how strong it is and how many people it covers.

    Effect size alone would promote a striking pattern among four people;
    coverage alone would promote a trivial pattern across everyone.
    """
    if respondents == 0:
        return 0.0

    coverage = min(row_total / respondents, 1.0)
    return round(min(association.cramers_v, 1.0) * 0.7 + coverage * 0.3, 4)


def _profile_insights(clusters: ClusterResult | None) -> list[Insight]:
    """Describe each respondent group in terms of what sets it apart.

    Groups whose description would repeat one already given are dropped.
    Clustering on categorical answers tends to split a real segment in two,
    and two sentences saying "this group chose Engineering and Strongly
    agree" are not two findings — they are one finding, told twice, which
    makes the page look padded and the analysis look confused.

    The larger group survives, since groups arrive sorted by size.
    """
    if clusters is None or not clusters.found_structure:
        return []

    insights: list[Insight] = []
    described: set[tuple[str, str]] = set()

    for index, group in enumerate(clusters.groups, start=1):
        insight = _profile_insight(index, group, clusters.respondents_clustered)
        if insight is None:
            continue

        signature = _profile_signature(group)
        if signature in described:
            continue

        described.add(signature)
        insights.append(insight)

    return insights


def _profile_signature(group: RespondentGroup) -> tuple[str, str]:
    """What a group's description amounts to, for spotting repeats.

    Keyed on the two answers the sentence actually quotes: groups that differ
    only in answers no reader is shown are, to that reader, the same group.
    """
    quoted = sorted((c.question, c.answer) for c in group.characteristics[:2])
    return tuple(f"{question}={answer}" for question, answer in quoted)  # type: ignore[return-value]


def _profile_insight(index: int, group: RespondentGroup, clustered: int) -> Insight | None:
    """Describe one group, or nothing when it has no description.

    A cluster can hold together in the encoded space and still have no answer
    that characterizes it. "Profile 3 exists" is not a finding.
    """
    if not group.has_description:
        return None

    top = group.characteristics[:2]
    traits = " and ".join(
        f"chose “{c.answer}” for “{c.question}” ({c.group_share}% of them, "
        f"against {c.overall_share}% overall)"
        for c in top
    )

    return Insight(
        text=(
            f"One group of {group.size} respondents ({group.share}% of those compared) {traits}."
        ),
        kind=InsightKind.PROFILE,
        relevance=round(min(group.share / 100, 1.0) * 0.4 + min(top[0].lift / 4, 1.0) * 0.6, 4),
        questions=[c.question for c in top],
        evidence={
            "group_size": group.size,
            "group_share": group.share,
            "respondents_clustered": clustered,
            "top_lift": top[0].lift,
        },
    )


def _opinion_insights(opinions: list[QuestionOpinion], respondents: int) -> list[Insight]:
    """Narrate questions the population clearly agrees on, or splits over."""
    insights: list[Insight] = []

    for opinion in opinions:
        if opinion.verdict is Verdict.POLARIZED and opinion.extreme_share is not None:
            insights.append(
                Insight(
                    text=(
                        f"“{opinion.question}” splits the room: {opinion.extreme_share}% "
                        f"of answers sit at one end of the scale or the other, with few "
                        f"in between. This is a divided population, not an undecided one."
                    ),
                    kind=InsightKind.POLARIZATION,
                    relevance=round(min(opinion.extreme_share / 100, 1.0) * 0.9, 4),
                    questions=[opinion.question],
                    evidence={
                        "extreme_share": opinion.extreme_share,
                        "modal_share": opinion.modal_share,
                        "dispersion": opinion.dispersion,
                    },
                )
            )

        elif opinion.verdict is Verdict.CONSENSUS:
            leading = max(opinion.counts.items(), key=lambda item: item[1])
            insights.append(
                Insight(
                    text=(
                        f"“{opinion.question}” is settled: {opinion.modal_share}% "
                        f"answered “{leading[0]}”."
                    ),
                    kind=InsightKind.CONSENSUS,
                    relevance=round(min(opinion.modal_share / 100, 1.0) * 0.6, 4),
                    questions=[opinion.question],
                    evidence={
                        "modal_answer": leading[0],
                        "modal_share": opinion.modal_share,
                        "respondents": respondents,
                    },
                )
            )

    return insights


def _participation_insights(summary: DatasetSummary) -> list[Insight]:
    """Flag a question people avoided.

    Worth a sentence because it changes how everything else about that
    question should be read: its statistics rest on fewer people than the
    reader assumes.
    """
    skipped = summary.lowest_response_rate
    if skipped is None or skipped.response_rate >= 90:
        return []

    return [
        Insight(
            text=(
                f"Only {skipped.response_rate}% of respondents answered "
                f"“{skipped.text}” — the least of any question. Read its results "
                f"as describing {skipped.answered} people, not all "
                f"{summary.respondents}."
            ),
            kind=InsightKind.PARTICIPATION,
            relevance=round((100 - skipped.response_rate) / 100 * 0.8, 4),
            questions=[skipped.text],
            evidence={
                "response_rate": skipped.response_rate,
                "answered": skipped.answered,
                "respondents": summary.respondents,
            },
        )
    ]


def _distribution_insights(summary: DatasetSummary) -> list[Insight]:
    """Point out a numeric question whose average misleads."""
    return [
        insight
        for distribution in summary.distributions
        if (insight := _skew_insight(distribution)) is not None
    ]


def _skew_insight(distribution: QuestionDistribution) -> Insight | None:
    """Narrate a mean pulled away from the median by extreme answers."""
    numeric = distribution.numeric
    if numeric is None or not numeric.is_skewed:
        return None

    direction = "above" if numeric.mean > numeric.median else "below"

    return Insight(
        text=(
            f"The average for “{distribution.text}” ({numeric.mean}) sits well "
            f"{direction} the midpoint ({numeric.median}), pulled by a few extreme "
            f"answers. The midpoint describes a typical respondent better."
        ),
        kind=InsightKind.DISTRIBUTION,
        relevance=0.35,
        questions=[distribution.text],
        evidence={
            "mean": numeric.mean,
            "median": numeric.median,
            "std_dev": numeric.std_dev,
        },
    )
