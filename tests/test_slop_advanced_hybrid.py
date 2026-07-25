import unittest

from app.tools.slop_advanced import (
    check_first_use_explainer,
    check_not_just_x_but_y,
    check_parallel_pair_endings,
    check_passive_weak_hedges,
    check_run_on_sentences,
    check_triple_parallel_noun_phrases,
)


class TestNotJustXButY(unittest.TestCase):
    def test_clean_text_passes(self) -> None:
        result = check_not_just_x_but_y("Delivered the migration ahead of schedule.")
        self.assertTrue(result.passed)

    def test_literal_formula_detected(self) -> None:
        result = check_not_just_x_but_y("This was not just a migration but a complete transformation.")
        self.assertFalse(result.passed)

    def test_paraphrased_variant_not_caught(self) -> None:
        """Documents the known limitation: only the literal form is
        caught here. A paraphrase needs a model sweep."""
        result = check_not_just_x_but_y("This wasn't only a migration, it was a complete transformation.")
        self.assertTrue(result.passed)


class TestTripleParallelNounPhrases(unittest.TestCase):
    def test_clean_text_passes(self) -> None:
        result = check_triple_parallel_noun_phrases("Led the migration successfully.")
        self.assertTrue(result.passed)

    def test_three_item_list_nominated(self) -> None:
        result = check_triple_parallel_noun_phrases("Led design, development, and deployment of the platform.")
        self.assertFalse(result.passed)


class TestPassiveWeakHedges(unittest.TestCase):
    def test_clean_text_passes(self) -> None:
        result = check_passive_weak_hedges("Led the migration and cut costs by 20 percent.")
        self.assertTrue(result.passed)

    def test_weak_hedge_phrase_detected(self) -> None:
        result = check_passive_weak_hedges("Participated in the migration project.")
        self.assertFalse(result.passed)

    def test_generic_passive_detected(self) -> None:
        result = check_passive_weak_hedges("The migration was completed by the team.")
        self.assertFalse(result.passed)


class TestParallelPairEndings(unittest.TestCase):
    def test_clean_text_passes(self) -> None:
        result = check_parallel_pair_endings("Led the migration. Cut costs by 20 percent.")
        self.assertTrue(result.passed)

    def test_repeated_ing_ending_nominated(self) -> None:
        result = check_parallel_pair_endings("Focused on scaling. Focused on optimizing.")
        self.assertFalse(result.passed)

    def test_same_last_word_nominated(self) -> None:
        result = check_parallel_pair_endings("Led the platform team. Managed the platform team.")
        self.assertFalse(result.passed)


class TestRunOnSentences(unittest.TestCase):
    def test_short_sentence_passes(self) -> None:
        result = check_run_on_sentences("Led the migration and cut costs.")
        self.assertTrue(result.passed)

    def test_long_sentence_nominated(self) -> None:
        long_sentence = " ".join(["word"] * 35) + "."
        result = check_run_on_sentences(long_sentence)
        self.assertFalse(result.passed)

    def test_many_conjunctions_nominated(self) -> None:
        result = check_run_on_sentences("Led the team and shipped the feature and cut costs and improved morale.")
        self.assertFalse(result.passed)


class TestFirstUseExplainer(unittest.TestCase):
    def test_no_known_terms_passes(self) -> None:
        result = check_first_use_explainer("Led the migration project.", known_terms=[])
        self.assertTrue(result.passed)

    def test_known_term_nominated(self) -> None:
        result = check_first_use_explainer("Worked on Project Falcon this quarter.", known_terms=["Project Falcon"])
        self.assertFalse(result.passed)

    def test_term_not_present_not_nominated(self) -> None:
        result = check_first_use_explainer("Led the migration.", known_terms=["Project Falcon"])
        self.assertTrue(result.passed)


if __name__ == "__main__":
    unittest.main()
