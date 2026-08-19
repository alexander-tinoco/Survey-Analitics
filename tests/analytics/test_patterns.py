"""Tests for clustering and polarization.

Clustering cannot be checked against a hand-computed number the way a
chi-square can, so it is checked against structure built on purpose: a frame
with three groups planted in it must yield three groups, and a frame of pure
noise must yield none. The second half matters more — k-means will always
return clusters, so the test that proves the guard works is the one where
there is nothing to find.
"""

import numpy as np
import pandas as pd
import pytest

from apps.analytics.engine.patterns import (
    MIN_SILHOUETTE,
    Verdict,
    find_groups,
    measure_opinion,
)

LIKERT = ["strongly disagree", "disagree", "neutral", "agree", "strongly agree"]


def planted_groups(size_per_group: int = 40) -> tuple[pd.DataFrame, dict[str, str]]:
    """Three groups that answer distinctly, with no overlap by construction."""
    rows = []
    for team, satisfaction, tooling in [
        ("Engineering", "Strongly agree", "Good"),
        ("Support", "Strongly disagree", "Poor"),
        ("Sales", "Neutral", "Average"),
    ]:
        rows.extend([(team, satisfaction, tooling)] * size_per_group)

    frame = pd.DataFrame(rows, columns=["Team", "Satisfaction", "Tooling"])
    types = {"Team": "categorical", "Satisfaction": "ordinal", "Tooling": "categorical"}
    return frame, types


def pure_noise(rows: int = 120) -> tuple[pd.DataFrame, dict[str, str]]:
    """Answers drawn independently — no structure exists to find."""
    generator = np.random.default_rng(seed=3)
    frame = pd.DataFrame(
        {
            "Q1": generator.choice(["a", "b", "c"], rows),
            "Q2": generator.choice(["x", "y", "z"], rows),
            "Q3": generator.choice(["p", "q", "r"], rows),
        }
    )
    return frame, dict.fromkeys(["Q1", "Q2", "Q3"], "categorical")


class TestFindingPlantedGroups:
    def test_three_planted_groups_are_recovered(self) -> None:
        frame, types = planted_groups()

        result = find_groups(frame, types)

        assert result.found_structure
        assert len(result.groups) == 3

    def test_recovered_groups_have_the_planted_sizes(self) -> None:
        frame, types = planted_groups(size_per_group=40)

        result = find_groups(frame, types)

        assert sorted(group.size for group in result.groups) == [40, 40, 40]

    def test_separation_is_reported(self) -> None:
        """Non-overlapping groups should score near the top of the range."""
        frame, types = planted_groups()

        result = find_groups(frame, types)

        assert result.silhouette > 0.9

    def test_each_group_is_described_by_its_answers(self) -> None:
        """ "Cluster 2" tells a reader nothing; the answers are the finding."""
        frame, types = planted_groups()

        result = find_groups(frame, types)

        assert all(group.has_description for group in result.groups)

        described = {
            (c.question, c.answer) for group in result.groups for c in group.characteristics
        }
        assert ("Team", "Support") in described
        assert ("Satisfaction", "Strongly disagree") in described

    def test_characteristic_answers_report_their_lift(self) -> None:
        """Each team is a third of the population and all of its own group,
        so the lift is 100/33.3 = 3.0.
        """
        frame, types = planted_groups()

        result = find_groups(frame, types)
        team_answers = [
            c for group in result.groups for c in group.characteristics if c.question == "Team"
        ]

        assert all(c.group_share == 100.0 for c in team_answers)
        assert all(c.lift == pytest.approx(3.0, abs=0.05) for c in team_answers)

    def test_group_shares_add_up_to_the_whole_population(self) -> None:
        frame, types = planted_groups()

        result = find_groups(frame, types)

        assert sum(group.size for group in result.groups) == len(frame)
        assert round(sum(group.share for group in result.groups)) == 100


class TestEncodingFairness:
    def test_a_question_with_many_options_does_not_dominate(self) -> None:
        """One-hot gives a question as many dimensions as it has options.

        Without per-question weighting, an eight-option question would carry
        eight times the weight of a rating scale in the distance between two
        respondents, and k-means would group people by whichever question
        happened to offer the most choices.

        Here the eight-option question is deliberately random while the
        two-option one carries the real split. The recovered groups must
        follow the signal, not the option count.
        """
        generator = np.random.default_rng(seed=7)
        size = 60
        frame = pd.DataFrame(
            {
                "Noise": generator.choice([f"opt{i}" for i in range(8)], size * 2),
                "Signal": ["Yes"] * size + ["No"] * size,
                "Echo": ["Yes"] * size + ["No"] * size,
            }
        )
        types = dict.fromkeys(["Noise", "Signal", "Echo"], "categorical")

        result = find_groups(frame, types)

        assert result.found_structure
        described = {c.question for group in result.groups for c in group.characteristics}
        assert "Signal" in described

    def test_ordinal_answers_reach_the_clustering_as_ranks(self) -> None:
        """Text answers cannot be coerced to numbers directly.

        Left to fall through, "Strongly agree" becomes NaN, the column
        flattens to a constant, and the ordering that the ordinal type exists
        to preserve is discarded before k-means ever sees it.
        """
        from apps.analytics.engine.patterns import _encode

        answers = pd.DataFrame({"Q": ["Strongly agree", "Neutral", "Strongly disagree"]})

        encoded, _ = _encode(answers, {"Q": "ordinal"}, {"Q": LIKERT})

        # Standardized ranks: distinct, and ordered like the scale.
        assert len(set(encoded.flatten())) == 3
        assert encoded[0][0] > encoded[1][0] > encoded[2][0]


class TestParsimony:
    def test_the_simplest_adequate_grouping_wins(self) -> None:
        """Silhouette rises with k on one-hot data, because splitting a group
        always buys a little separation. Taking the maximum oversegments, so
        any k within the tolerance of the best is treated as equally good and
        the smallest wins.
        """
        from apps.analytics.engine.patterns import _most_parsimonious

        labels_two = np.array([0, 1])
        labels_five = np.array([0, 1, 2, 3, 4])
        scored = [(2, labels_two, 0.70), (5, labels_five, 0.75)]

        chosen, score = _most_parsimonious(scored)

        assert list(chosen) == list(labels_two)
        assert score == 0.70

    def test_a_clearly_better_split_still_wins(self) -> None:
        """Parsimony is a tie-break, not a preference for two groups."""
        from apps.analytics.engine.patterns import _most_parsimonious

        scored = [(2, np.array([0, 1]), 0.30), (4, np.array([0, 1, 2, 3]), 0.80)]

        chosen, score = _most_parsimonious(scored)

        assert len(chosen) == 4
        assert score == 0.80

    def test_nothing_scored_yields_nothing(self) -> None:
        from apps.analytics.engine.patterns import _most_parsimonious

        assert _most_parsimonious([]) is None


class TestRefusingToInventGroups:
    def test_noise_yields_no_groups(self) -> None:
        """The guard that matters: k-means will always return clusters, so
        this is what stops the report from labelling random answers as
        segments.
        """
        frame, types = pure_noise()

        result = find_groups(frame, types)

        assert not result.found_structure
        assert result.groups == []

    def test_the_rejection_is_explained(self) -> None:
        """ "No groups" without a reason reads as a failure, not a finding."""
        frame, types = pure_noise()

        result = find_groups(frame, types)

        assert "do not separate" in result.rejection_reason

    def test_a_single_question_cannot_be_clustered(self) -> None:
        frame = pd.DataFrame({"Only": ["a", "b"] * 60})

        result = find_groups(frame, {"Only": "categorical"})

        assert not result.found_structure
        assert "two questions" in result.rejection_reason

    def test_too_few_respondents_are_not_clustered(self) -> None:
        """Below this k-means separates individuals, not segments."""
        frame = pd.DataFrame({"Q1": ["a", "b", "c"], "Q2": ["x", "y", "z"]})

        result = find_groups(frame, {"Q1": "categorical", "Q2": "categorical"})

        assert not result.found_structure
        assert "Too few respondents" in result.rejection_reason

    def test_free_text_is_excluded_from_clustering(self) -> None:
        frame = pd.DataFrame(
            {
                "Comment": [f"a distinct remark number {n}" for n in range(60)],
                "Other": [f"another remark number {n}" for n in range(60)],
            }
        )

        result = find_groups(frame, dict.fromkeys(["Comment", "Other"], "free_text"))

        assert not result.found_structure


class TestDeterminism:
    def test_the_same_data_always_yields_the_same_groups(self) -> None:
        """A report whose segments change between page loads is not a report."""
        frame, types = planted_groups()

        first = find_groups(frame, types)
        second = find_groups(frame, types)

        assert [g.size for g in first.groups] == [g.size for g in second.groups]
        assert first.silhouette == second.silhouette


class TestPolarization:
    def test_a_question_answered_at_both_ends_is_polarized(self) -> None:
        """45 at each end, 10 in the middle: 90% extreme, 10% middle.

        This is the shape that describes a population in two camps.
        """
        answers = ["Strongly agree"] * 45 + ["Strongly disagree"] * 45 + ["Neutral"] * 10
        frame = pd.DataFrame({"Q": answers})

        opinion = measure_opinion(frame, {"Q": "ordinal"}, {"Q": LIKERT})[0]

        assert opinion.verdict is Verdict.POLARIZED
        assert opinion.extreme_share == 90.0

    def test_a_question_everyone_agrees_on_is_consensus(self) -> None:
        """80 of 100 chose the same answer."""
        answers = ["Agree"] * 80 + ["Neutral"] * 15 + ["Disagree"] * 5
        frame = pd.DataFrame({"Q": answers})

        opinion = measure_opinion(frame, {"Q": "ordinal"}, {"Q": LIKERT})[0]

        assert opinion.verdict is Verdict.CONSENSUS
        assert opinion.modal_share == 80.0

    def test_evenly_spread_answers_are_divided_not_polarized(self) -> None:
        """The distinction the whole measure exists for.

        Twenty at every point of the scale is a population that has not
        settled, not one split into two camps — and calling it polarized
        would invent a conflict that is not there.
        """
        answers = [point.title() for point in LIKERT for _ in range(20)]
        frame = pd.DataFrame({"Q": answers})

        opinion = measure_opinion(frame, {"Q": "ordinal"}, {"Q": LIKERT})[0]

        assert opinion.verdict is Verdict.DIVIDED
        assert opinion.extreme_share == 40.0

    def test_strong_answers_in_one_direction_are_not_polarized(self) -> None:
        """Everyone at one end agrees; only both ends means camps."""
        answers = ["Strongly agree"] * 70 + ["Agree"] * 30
        frame = pd.DataFrame({"Q": answers})

        opinion = measure_opinion(frame, {"Q": "ordinal"}, {"Q": LIKERT})[0]

        assert opinion.verdict is not Verdict.POLARIZED

    def test_categorical_questions_have_no_extremes(self) -> None:
        """Departments have no ends, so polarization does not apply."""
        frame = pd.DataFrame({"Team": ["Sales"] * 50 + ["Support"] * 50})

        opinion = measure_opinion(frame, {"Team": "categorical"}, {})[0]

        assert opinion.extreme_share is None
        assert opinion.verdict is not Verdict.POLARIZED


class TestDispersion:
    def test_unanimous_answers_have_zero_dispersion(self) -> None:
        frame = pd.DataFrame({"Q": ["Yes"] * 50})

        opinion = measure_opinion(frame, {"Q": "categorical"}, {})[0]

        assert opinion.dispersion == 0.0

    def test_a_perfectly_even_split_has_full_dispersion(self) -> None:
        """Normalized entropy is 1 when every option is equally likely.

        Two options at 50/50: -(0.5*ln0.5 + 0.5*ln0.5) / ln2 = ln2/ln2 = 1.
        """
        frame = pd.DataFrame({"Q": ["Yes"] * 50 + ["No"] * 50})

        opinion = measure_opinion(frame, {"Q": "categorical"}, {})[0]

        assert opinion.dispersion == 1.0

    def test_dispersion_is_comparable_across_option_counts(self) -> None:
        """Raw entropy grows with the number of options regardless of how
        divided people are; normalizing is what makes a three-option and a
        five-option question comparable.
        """
        three = pd.DataFrame({"Q": ["a", "b", "c"] * 30})
        five = pd.DataFrame({"Q": ["a", "b", "c", "d", "e"] * 30})

        three_way = measure_opinion(three, {"Q": "categorical"}, {})[0]
        five_way = measure_opinion(five, {"Q": "categorical"}, {})[0]

        assert three_way.dispersion == 1.0
        assert five_way.dispersion == 1.0


class TestNotability:
    @pytest.mark.parametrize(
        ("verdict", "expected"),
        [
            (Verdict.CONSENSUS, True),
            (Verdict.POLARIZED, True),
            (Verdict.DIVIDED, False),
            (Verdict.MIXED, False),
        ],
    )
    def test_only_clear_verdicts_are_surfaced(self, verdict: Verdict, expected: bool) -> None:
        """A dashboard that highlights every question highlights nothing."""
        from apps.analytics.engine.patterns import QuestionOpinion

        opinion = QuestionOpinion(
            question="Q",
            verdict=verdict,
            modal_share=50.0,
            extreme_share=None,
            dispersion=0.5,
        )

        assert opinion.is_notable is expected

    def test_questions_with_no_answers_are_skipped(self) -> None:
        frame = pd.DataFrame({"Q": [None, None, None]})

        assert measure_opinion(frame, {"Q": "categorical"}, {}) == []


class TestInternalGuards:
    """Branches reached only by unusual data, exercised directly.

    These are the paths that run when a survey is malformed or a scale is
    degenerate. They are the least travelled code in the module and the most
    likely to be wrong when they finally matter.
    """

    def test_an_answer_with_no_overall_presence_has_no_lift(self) -> None:
        """Guards a division by zero when an answer is absent overall."""
        from apps.analytics.engine.patterns import CharacteristicAnswer

        orphan = CharacteristicAnswer(question="Q", answer="a", group_share=50.0, overall_share=0.0)

        assert orphan.lift == 0.0

    def test_a_two_point_scale_has_no_middle(self) -> None:
        """Polarization needs a middle to be empty; a yes/no scale has none,
        so it must not be reported as two camps.
        """
        answers = ["Yes"] * 50 + ["No"] * 50
        frame = pd.DataFrame({"Q": answers})

        opinion = measure_opinion(frame, {"Q": "ordinal"}, {"Q": ["yes", "no"]})[0]

        assert opinion.extreme_share is None
        assert opinion.verdict is not Verdict.POLARIZED

    def test_a_scale_with_no_answers_has_no_extremes(self) -> None:
        from apps.analytics.engine.patterns import _extreme_share, _middle_share

        empty = pd.Series(dtype=int)

        assert _extreme_share(empty, LIKERT) is None
        assert _middle_share(empty, LIKERT) == 1.0

    def test_clustering_stops_when_no_k_fits(self) -> None:
        """Every respondent identical: k-means cannot produce two groups, so
        there is no partition to score.
        """
        frame = pd.DataFrame({"Q1": ["a"] * 40, "Q2": ["x"] * 40})

        result = find_groups(frame, {"Q1": "categorical", "Q2": "categorical"})

        assert not result.found_structure

    def test_clustering_is_refused_when_the_ceiling_falls_below_two_groups(
        self,
    ) -> None:
        """Enough respondents to reach the encoder, too few for two groups of
        the minimum size. The search has no valid k to try at all.
        """
        from apps.analytics.engine.patterns import _best_clustering, _encode

        frame = pd.DataFrame({"Q1": ["a", "b"] * 8, "Q2": ["x", "y"] * 8})
        types = {"Q1": "categorical", "Q2": "categorical"}
        encoded, _ = _encode(frame, types, {})

        assert _best_clustering(encoded, frame, types, {}) is None

    def test_a_question_nobody_answered_describes_no_group(self) -> None:
        """A column that is entirely blank cannot characterize anyone, and
        must be skipped rather than divided by zero.
        """
        from apps.analytics.engine.patterns import _characteristics_of

        members = pd.DataFrame({"Blank": [None, None], "Real": ["a", "a"]})

        found = _characteristics_of(members, members, ["Blank", "Real"])

        assert all(c.question != "Blank" for c in found)

    def test_a_short_scale_is_treated_as_having_no_middle(self) -> None:
        """_middle_share guards the same degenerate scale _extreme_share does.

        Nothing reaches it through _verdict today, because a scale that short
        already returns None for its extremes. The guard stands on its own so
        the two cannot drift apart.
        """
        from apps.analytics.engine.patterns import _middle_share

        counts = pd.Series({"yes": 30, "no": 20})

        assert _middle_share(counts, ["yes", "no"]) == 1.0

    def test_the_null_skips_permutations_that_cannot_reach_a_given_k(self) -> None:
        """A shuffled frame with few distinct combinations cannot be split
        into every candidate k. Those k are skipped rather than scored, so a
        partition the data never achieved cannot raise the null.
        """
        from apps.analytics.engine.patterns import _null_silhouette

        frame = pd.DataFrame({"Q1": ["a"] * 30, "Q2": ["x", "y"] * 15})
        types = {"Q1": "categorical", "Q2": "categorical"}

        assert _null_silhouette(frame, types, {}) >= 0.0

    def test_a_null_permutation_that_cannot_cluster_scores_nothing(self) -> None:
        """When no permutation yields a valid partition, the null is zero and
        any real structure clears it.
        """
        from apps.analytics.engine.patterns import _null_silhouette

        frame = pd.DataFrame({"Q1": ["a", "b"] * 8, "Q2": ["x", "y"] * 8})

        assert _null_silhouette(frame, dict.fromkeys(["Q1", "Q2"], "categorical"), {}) == 0.0

    def test_a_group_with_no_distinguishing_answer_says_so(self) -> None:
        """A cluster can hold together in the encoded space and still have
        nothing that describes it to a reader.
        """
        from apps.analytics.engine.patterns import RespondentGroup

        undescribed = RespondentGroup(label=0, size=10, share=25.0, characteristics=[])

        assert undescribed.has_description is False


def test_silhouette_threshold_is_above_zero() -> None:
    """A threshold of zero would accept any partition k-means returned."""
    assert MIN_SILHOUETTE > 0
