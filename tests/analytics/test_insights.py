"""Tests for insight generation.

Two properties matter more than the wording:

* A sentence must not contradict the statistics it came from. Several tests
  parse the numbers back out of the text and compare them to the evidence.
* Nothing unreliable produces a sentence. Silence is a correct output; a
  confident sentence about noise is the failure this layer exists to avoid.
"""

import re

import numpy as np
import pandas as pd
import pytest

from apps.analytics.engine.descriptive import summarize
from apps.analytics.engine.insights import (
    MAX_INSIGHTS,
    InsightKind,
    generate,
)
from apps.analytics.engine.patterns import (
    CharacteristicAnswer,
    ClusterResult,
    QuestionOpinion,
    RespondentGroup,
    Verdict,
    find_groups,
    measure_opinion,
)
from apps.analytics.engine.relational import analyze, associate

LIKERT = ["strongly disagree", "disagree", "neutral", "agree", "strongly agree"]


def percentages_in(text: str) -> list[float]:
    """Every percentage the sentence states."""
    return [float(match) for match in re.findall(r"(\d+\.?\d*)%", text)]


def linked_answers(counts: dict[tuple[str, str], int]) -> tuple[pd.Series, pd.Series]:
    rows: list[str] = []
    columns: list[str] = []
    for (row_value, column_value), count in counts.items():
        rows.extend([row_value] * count)
        columns.extend([column_value] * count)
    return pd.Series(rows), pd.Series(columns)


def empty_clusters() -> ClusterResult:
    return ClusterResult(groups=[], silhouette=0.0, respondents_clustered=0)


class TestRelationshipSentences:
    def test_a_strong_relationship_is_stated_in_plain_language(self) -> None:
        """The product brief's own example.

        100 respondents. Of the 50 who said "Unsatisfied", 40 also reported
        "Low" support: 40/50 = 80.0%. Across everyone, "Low" was chosen by
        45 of 100 = 45.0%.
        """
        rows, columns = linked_answers(
            {
                ("Unsatisfied", "Low"): 40,
                ("Unsatisfied", "High"): 10,
                ("Satisfied", "Low"): 5,
                ("Satisfied", "High"): 45,
            }
        )
        association = associate("Satisfaction", "Support availability", rows, columns)
        summary = summarize(pd.DataFrame({"x": range(100)}), {"x": "numeric"})

        insights = generate(summary, [association], empty_clusters(), [])
        relationship = next(i for i in insights if i.kind is InsightKind.RELATIONSHIP)

        assert "80.0%" in relationship.text
        assert "45.0%" in relationship.text
        assert "Unsatisfied" in relationship.text
        assert "Low" in relationship.text

    def test_the_sentence_agrees_with_its_own_evidence(self) -> None:
        """A claim the reader cannot check is a claim they should not trust."""
        rows, columns = linked_answers(
            {
                ("Unsatisfied", "Low"): 40,
                ("Unsatisfied", "High"): 10,
                ("Satisfied", "Low"): 5,
                ("Satisfied", "High"): 45,
            }
        )
        association = associate("Satisfaction", "Support", rows, columns)
        summary = summarize(pd.DataFrame({"x": range(100)}), {"x": "numeric"})

        relationship = next(
            i
            for i in generate(summary, [association], empty_clusters(), [])
            if i.kind is InsightKind.RELATIONSHIP
        )

        stated = percentages_in(relationship.text)
        assert relationship.evidence["row_share"] in stated
        assert relationship.evidence["overall_share"] in stated

    def test_an_unreliable_association_produces_no_sentence(self) -> None:
        """It failed its own assumptions, so its p-value means nothing.

        Narrating it would launder an untrustworthy number into a confident
        claim — the exact failure this layer exists to prevent.
        """
        rows, columns = linked_answers({("A", "X"): 3, ("A", "Y"): 1, ("B", "X"): 1, ("B", "Y"): 3})
        association = associate("Q1", "Q2", rows, columns)
        summary = summarize(pd.DataFrame({"x": range(8)}), {"x": "numeric"})

        assert association.is_reliable is False
        insights = generate(summary, [association], empty_clusters(), [])

        assert not any(i.kind is InsightKind.RELATIONSHIP for i in insights)

    def test_unrelated_questions_produce_no_sentences(self) -> None:
        """Eight independent questions make 28 pairs. At p < 0.05 roughly one
        would look significant by chance, and narrating it would invent a
        finding out of nothing. Correction plus the lift floor keep the page
        empty, which is the right answer for random data.
        """
        generator = np.random.default_rng(seed=13)
        frame = pd.DataFrame({f"Q{n}": generator.choice(["a", "b", "c"], 200) for n in range(8)})
        types = {f"Q{n}": "categorical" for n in range(8)}
        associations = analyze(frame, types)
        summary = summarize(frame, types)

        insights = generate(summary, associations, empty_clusters(), [])

        assert not any(i.kind is InsightKind.RELATIONSHIP for i in insights)

    def test_a_relationship_too_weak_to_mention_is_skipped(self) -> None:
        """ "52% against 50% overall" is arithmetic, not a finding."""
        rows, columns = linked_answers(
            {
                ("A", "X"): 260,
                ("A", "Y"): 240,
                ("B", "X"): 240,
                ("B", "Y"): 260,
            }
        )
        association = associate("Q1", "Q2", rows, columns)
        summary = summarize(pd.DataFrame({"x": range(1000)}), {"x": "numeric"})

        insights = generate(summary, [association], empty_clusters(), [])

        assert not any(i.kind is InsightKind.RELATIONSHIP for i in insights)

    def test_a_pattern_among_too_few_people_is_skipped(self) -> None:
        """A striking pattern among 4 of 200 describes almost nobody."""
        rows, columns = linked_answers(
            {
                ("Rare", "X"): 4,
                ("Common", "X"): 98,
                ("Common", "Y"): 98,
            }
        )
        association = associate("Q1", "Q2", rows, columns)
        summary = summarize(pd.DataFrame({"x": range(200)}), {"x": "numeric"})

        insights = generate(summary, [association], empty_clusters(), [])
        relationships = [i for i in insights if i.kind is InsightKind.RELATIONSHIP]

        assert all(i.evidence["row_answer"] != "Rare" for i in relationships)


class TestProfileSentences:
    def test_a_group_is_described_by_its_answers(self) -> None:
        frame = pd.DataFrame(
            {
                "Team": ["Engineering"] * 40 + ["Support"] * 40 + ["Sales"] * 40,
                "Tooling": ["Good"] * 40 + ["Poor"] * 40 + ["Average"] * 40,
            }
        )
        types = {"Team": "categorical", "Tooling": "categorical"}
        clusters = find_groups(frame, types)
        summary = summarize(frame, types)

        insights = generate(summary, [], clusters, [])
        profiles = [i for i in insights if i.kind is InsightKind.PROFILE]

        assert profiles
        assert any("respondents" in i.text for i in profiles)

    def test_an_undescribable_group_produces_no_sentence(self) -> None:
        """ "Profile 3 exists" is not a finding."""
        clusters = ClusterResult(
            groups=[RespondentGroup(label=0, size=30, share=50.0, characteristics=[])],
            silhouette=0.6,
            respondents_clustered=60,
        )
        summary = summarize(pd.DataFrame({"x": range(60)}), {"x": "numeric"})

        insights = generate(summary, [], clusters, [])

        assert not any(i.kind is InsightKind.PROFILE for i in insights)

    def test_groups_described_identically_are_told_once(self) -> None:
        """Clustering on categorical answers tends to split a real segment in
        two. Two sentences saying the same thing are one finding told twice,
        which makes the page look padded and the analysis look confused.
        """

        def group(label: int, size: int) -> RespondentGroup:
            return RespondentGroup(
                label=label,
                size=size,
                share=size / 2.0,
                characteristics=[
                    CharacteristicAnswer(
                        question="Team",
                        answer="Engineering",
                        group_share=95.0,
                        overall_share=30.0,
                    ),
                    CharacteristicAnswer(
                        question="Mood",
                        answer="Strongly agree",
                        group_share=44.0,
                        overall_share=14.0,
                    ),
                ],
            )

        clusters = ClusterResult(
            groups=[group(0, 60), group(1, 40)],
            silhouette=0.5,
            respondents_clustered=200,
        )
        summary = summarize(pd.DataFrame({"x": range(200)}), {"x": "numeric"})

        profiles = [i for i in generate(summary, [], clusters, []) if i.kind is InsightKind.PROFILE]

        assert len(profiles) == 1
        # The larger group survives: groups arrive sorted by size.
        assert "60 respondents" in profiles[0].text

    def test_genuinely_different_groups_are_both_reported(self) -> None:
        clusters = ClusterResult(
            groups=[
                RespondentGroup(
                    label=0,
                    size=60,
                    share=30.0,
                    characteristics=[
                        CharacteristicAnswer(
                            question="Team",
                            answer="Engineering",
                            group_share=95.0,
                            overall_share=30.0,
                        )
                    ],
                ),
                RespondentGroup(
                    label=1,
                    size=50,
                    share=25.0,
                    characteristics=[
                        CharacteristicAnswer(
                            question="Team",
                            answer="Support",
                            group_share=93.0,
                            overall_share=28.0,
                        )
                    ],
                ),
            ],
            silhouette=0.5,
            respondents_clustered=200,
        )
        summary = summarize(pd.DataFrame({"x": range(200)}), {"x": "numeric"})

        profiles = [i for i in generate(summary, [], clusters, []) if i.kind is InsightKind.PROFILE]

        assert len(profiles) == 2

    def test_no_structure_produces_no_profile_sentences(self) -> None:
        clusters = ClusterResult(
            groups=[], silhouette=0.0, respondents_clustered=100, rejection_reason="none"
        )
        summary = summarize(pd.DataFrame({"x": range(100)}), {"x": "numeric"})

        insights = generate(summary, [], clusters, [])

        assert not any(i.kind is InsightKind.PROFILE for i in insights)

    def test_a_profile_sentence_quotes_its_group_size(self) -> None:
        clusters = ClusterResult(
            groups=[
                RespondentGroup(
                    label=0,
                    size=25,
                    share=41.7,
                    characteristics=[
                        CharacteristicAnswer(
                            question="Team",
                            answer="Support",
                            group_share=88.0,
                            overall_share=30.0,
                        )
                    ],
                )
            ],
            silhouette=0.6,
            respondents_clustered=60,
        )
        summary = summarize(pd.DataFrame({"x": range(60)}), {"x": "numeric"})

        profile = next(
            i for i in generate(summary, [], clusters, []) if i.kind is InsightKind.PROFILE
        )

        assert "25 respondents" in profile.text
        assert "88.0%" in profile.text
        assert "30.0%" in profile.text


class TestOpinionSentences:
    def test_a_polarized_question_is_named_as_divided_not_undecided(self) -> None:
        """The distinction the pattern layer exists to make, carried into
        the wording: a split population is not an undecided one.
        """
        answers = ["Strongly agree"] * 45 + ["Strongly disagree"] * 45 + ["Neutral"] * 10
        frame = pd.DataFrame({"Trust in leadership": answers})
        opinions = measure_opinion(
            frame, {"Trust in leadership": "ordinal"}, {"Trust in leadership": LIKERT}
        )
        summary = summarize(frame, {"Trust in leadership": "ordinal"})

        insight = next(
            i
            for i in generate(summary, [], empty_clusters(), opinions)
            if i.kind is InsightKind.POLARIZATION
        )

        assert "90.0%" in insight.text
        assert "divided population, not an undecided one" in insight.text

    def test_a_settled_question_is_stated_with_its_answer(self) -> None:
        answers = ["Agree"] * 80 + ["Neutral"] * 15 + ["Disagree"] * 5
        frame = pd.DataFrame({"Q": answers})
        opinions = measure_opinion(frame, {"Q": "ordinal"}, {"Q": LIKERT})
        summary = summarize(frame, {"Q": "ordinal"})

        insight = next(
            i
            for i in generate(summary, [], empty_clusters(), opinions)
            if i.kind is InsightKind.CONSENSUS
        )

        assert "80.0%" in insight.text
        assert "Agree" in insight.text

    def test_an_evenly_split_question_produces_no_sentence(self) -> None:
        """Neither settled nor polarized: there is nothing to say about it."""
        answers = [point.title() for point in LIKERT for _ in range(20)]
        frame = pd.DataFrame({"Q": answers})
        opinions = measure_opinion(frame, {"Q": "ordinal"}, {"Q": LIKERT})
        summary = summarize(frame, {"Q": "ordinal"})

        insights = generate(summary, [], empty_clusters(), opinions)

        assert opinions[0].verdict is Verdict.DIVIDED
        assert not any(
            i.kind in {InsightKind.CONSENSUS, InsightKind.POLARIZATION} for i in insights
        )


class TestParticipationAndDistribution:
    def test_a_skipped_question_is_flagged_with_its_real_base(self) -> None:
        """The sentence has to say who the numbers describe: quoting a
        percentage of 100 respondents when 60 answered overstates it.
        """
        frame = pd.DataFrame(
            {
                "Answered": ["a"] * 100,
                "Avoided": ["a"] * 60 + [None] * 40,
            }
        )
        types = {"Answered": "categorical", "Avoided": "categorical"}
        summary = summarize(frame, types)

        insight = next(
            i
            for i in generate(summary, [], empty_clusters(), [])
            if i.kind is InsightKind.PARTICIPATION
        )

        assert "60.0%" in insight.text
        assert "60 people, not all 100" in insight.text

    def test_full_participation_produces_no_sentence(self) -> None:
        frame = pd.DataFrame({"Q1": ["a"] * 50, "Q2": ["b"] * 50})
        summary = summarize(frame, dict.fromkeys(["Q1", "Q2"], "categorical"))

        insights = generate(summary, [], empty_clusters(), [])

        assert not any(i.kind is InsightKind.PARTICIPATION for i in insights)

    def test_a_misleading_average_is_called_out(self) -> None:
        """1,1,1,1,100: mean 20.8, median 1."""
        frame = pd.DataFrame({"Budget": [1, 1, 1, 1, 100]})
        summary = summarize(frame, {"Budget": "numeric"})

        insight = next(
            i
            for i in generate(summary, [], empty_clusters(), [])
            if i.kind is InsightKind.DISTRIBUTION
        )

        assert "20.8" in insight.text
        assert "midpoint describes a typical respondent better" in insight.text

    def test_a_symmetric_distribution_produces_no_sentence(self) -> None:
        frame = pd.DataFrame({"Q": [1, 2, 3, 4, 5]})
        summary = summarize(frame, {"Q": "numeric"})

        insights = generate(summary, [], empty_clusters(), [])

        assert not any(i.kind is InsightKind.DISTRIBUTION for i in insights)


class TestRanking:
    def test_the_strongest_finding_is_first(self) -> None:
        """A reader gets through the first three sentences, not the last ten."""
        rows, columns = linked_answers(
            {("A", "X"): 90, ("A", "Y"): 10, ("B", "X"): 10, ("B", "Y"): 90}
        )
        strong = associate("Q1", "Q2", rows, columns)
        frame = pd.DataFrame({"Q": [1, 1, 1, 1, 100]})
        summary = summarize(frame, {"Q": "numeric"})

        insights = generate(summary, [strong], empty_clusters(), [])

        assert insights[0].kind is InsightKind.RELATIONSHIP
        assert insights == sorted(insights, key=lambda i: -i.relevance)

    def test_the_list_is_capped(self) -> None:
        """A page of forty insights is a page nobody reads."""
        opinions = [
            QuestionOpinion(
                question=f"Q{n}",
                verdict=Verdict.CONSENSUS,
                modal_share=95.0,
                extreme_share=None,
                dispersion=0.1,
                counts={"Yes": 95, "No": 5},
            )
            for n in range(30)
        ]
        summary = summarize(pd.DataFrame({"x": range(100)}), {"x": "numeric"})

        insights = generate(summary, [], empty_clusters(), opinions)

        assert len(insights) == MAX_INSIGHTS

    def test_a_dataset_with_nothing_to_say_yields_nothing(self) -> None:
        """Silence is a correct output."""
        frame = pd.DataFrame({"Q": ["a"] * 30 + ["b"] * 30})
        summary = summarize(frame, {"Q": "categorical"})

        assert generate(summary, [], empty_clusters(), []) == []


class TestGuards:
    """Branches that only run on degenerate input.

    Each guards a division by zero or an empty table — the states a dataset
    reaches when ingestion produced something unusual, and the ones most
    likely to be wrong when they finally matter.
    """

    def test_an_empty_table_yields_no_sentence(self) -> None:
        from apps.analytics.engine.insights import _strongest_cell
        from apps.analytics.engine.relational import Association, ContingencyTable

        empty = Association(
            row_question="A",
            column_question="B",
            table=ContingencyTable(row_labels=[], column_labels=[], counts=[]),
            chi_square=0.0,
            p_value=0.001,
            degrees_of_freedom=1,
            cramers_v=0.5,
            respondents=0,
            is_reliable=True,
        )

        assert _strongest_cell(empty) is None

    def test_a_column_nobody_chose_is_skipped(self) -> None:
        """An answer with no respondents overall has no rate to beat."""
        from apps.analytics.engine.insights import _strongest_cell
        from apps.analytics.engine.relational import Association, ContingencyTable

        table = ContingencyTable(
            row_labels=["a", "b"],
            column_labels=["chosen", "never"],
            counts=[[40, 0], [10, 0]],
        )
        association = Association(
            row_question="A",
            column_question="B",
            table=table,
            chi_square=1.0,
            p_value=0.001,
            degrees_of_freedom=1,
            cramers_v=0.5,
            respondents=50,
            is_reliable=True,
        )

        cell = _strongest_cell(association)

        assert cell is None or cell[1] != "never"

    def test_a_row_covering_almost_nobody_is_not_narrated(self) -> None:
        """A striking pattern among 4 of 200 describes almost nobody.

        Built directly rather than through associate(), because a table this
        lopsided also fails its reliability check and would be filtered out
        before the row-coverage rule ever ran.
        """
        from apps.analytics.engine.insights import _strongest_cell
        from apps.analytics.engine.relational import Association, ContingencyTable

        table = ContingencyTable(
            row_labels=["Rare", "Common"],
            column_labels=["X", "Y"],
            counts=[[4, 0], [98, 98]],
        )
        association = Association(
            row_question="A",
            column_question="B",
            table=table,
            chi_square=4.0,
            p_value=0.001,
            degrees_of_freedom=1,
            cramers_v=0.5,
            respondents=200,
            is_reliable=True,
        )

        assert _strongest_cell(association) is None

    def test_a_significant_association_with_no_notable_cell_is_skipped(self) -> None:
        """Significant overall, but no single combination stands out enough
        to state. The association is real; there is still nothing to say.
        """
        from apps.analytics.engine.relational import Association, ContingencyTable

        table = ContingencyTable(
            row_labels=["a", "b"],
            column_labels=["x", "y"],
            counts=[[52, 48], [48, 52]],
        )
        association = Association(
            row_question="Q1",
            column_question="Q2",
            table=table,
            chi_square=6.0,
            p_value=0.0001,
            degrees_of_freedom=1,
            cramers_v=0.4,
            respondents=200,
            is_reliable=True,
            adjusted_p_value=0.0001,
        )
        summary = summarize(pd.DataFrame({"x": range(200)}), {"x": "numeric"})

        assert association.is_significant is True
        assert not any(
            i.kind is InsightKind.RELATIONSHIP
            for i in generate(summary, [association], empty_clusters(), [])
        )

    def test_relevance_is_zero_when_there_are_no_respondents(self) -> None:
        from apps.analytics.engine.insights import _relationship_relevance
        from apps.analytics.engine.relational import Association, ContingencyTable

        association = Association(
            row_question="A",
            column_question="B",
            table=ContingencyTable(row_labels=[], column_labels=[], counts=[]),
            chi_square=0.0,
            p_value=1.0,
            degrees_of_freedom=1,
            cramers_v=0.0,
            respondents=0,
            is_reliable=True,
        )

        assert _relationship_relevance(association, row_total=0, respondents=0) == 0.0

    def test_an_insignificant_association_is_skipped_before_any_work(self) -> None:
        """The filter runs before the table is scanned, not after."""
        rows, columns = linked_answers(
            {("A", "X"): 25, ("A", "Y"): 25, ("B", "X"): 25, ("B", "Y"): 25}
        )
        association = associate("Q1", "Q2", rows, columns)
        summary = summarize(pd.DataFrame({"x": range(100)}), {"x": "numeric"})

        assert association.is_significant is False
        assert not any(
            i.kind is InsightKind.RELATIONSHIP
            for i in generate(summary, [association], empty_clusters(), [])
        )


class TestEvidence:
    def test_every_insight_carries_the_questions_it_is_about(self) -> None:
        """The interface links each sentence back to its data."""
        rows, columns = linked_answers(
            {("A", "X"): 90, ("A", "Y"): 10, ("B", "X"): 10, ("B", "Y"): 90}
        )
        association = associate("Q1", "Q2", rows, columns)
        summary = summarize(pd.DataFrame({"x": range(200)}), {"x": "numeric"})

        for insight in generate(summary, [association], empty_clusters(), []):
            assert insight.questions
            assert insight.evidence

    @pytest.mark.parametrize("relevance_bound", [0.0, 1.0])
    def test_relevance_stays_within_range(self, relevance_bound: float) -> None:
        rows, columns = linked_answers({("A", "X"): 100, ("B", "Y"): 100})
        association = associate("Q1", "Q2", rows, columns)
        summary = summarize(pd.DataFrame({"x": range(200)}), {"x": "numeric"})

        for insight in generate(summary, [association], empty_clusters(), []):
            assert 0.0 <= insight.relevance <= 1.0
