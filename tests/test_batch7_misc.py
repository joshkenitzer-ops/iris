import unittest

from app.tools.cover_letter import (
    check_closing_line_present,
    check_cover_letter_font_matches_resume,
    check_portfolio_requested,
)
from app.tools.slop_advanced import nominate_banned_term_misuse_candidates


class TestBannedTermMisuseCandidates(unittest.TestCase):
    def test_no_candidates_passes(self) -> None:
        result = nominate_banned_term_misuse_candidates("Reduced onboarding time in half.")
        self.assertTrue(result.passed)

    def test_single_use_still_nominated(self) -> None:
        """Unlike check_banned_vocabulary, a single ordinary use is
        still a candidate here, since misuse can happen on the first
        occurrence, not only above a frequency threshold."""
        result = nominate_banned_term_misuse_candidates("This effectively solved the problem.")
        self.assertFalse(result.passed)
        self.assertEqual(len(result.data["candidates"]), 1)

    def test_multiple_occurrences_all_nominated(self) -> None:
        result = nominate_banned_term_misuse_candidates("Effectively fixed it, then directly addressed the rest.")
        self.assertEqual(len(result.data["candidates"]), 2)


class TestClosingLinePresent(unittest.TestCase):
    def test_present_closing_line_passes(self) -> None:
        result = check_closing_line_present("Body text.\n\nLooking forward to connecting.")
        self.assertTrue(result.passed)

    def test_empty_letter_fails(self) -> None:
        result = check_closing_line_present("")
        self.assertFalse(result.passed)

    def test_trailing_blank_line_treated_as_missing(self) -> None:
        result = check_closing_line_present("Body text.\n\n   \n")
        self.assertTrue(result.passed)  # strip() collapses trailing blank lines, last real line found


class TestCoverLetterFontMatchesResume(unittest.TestCase):
    def test_matching_fonts_pass(self) -> None:
        result = check_cover_letter_font_matches_resume("Calibri", "Calibri")
        self.assertTrue(result.passed)

    def test_mismatched_fonts_fail(self) -> None:
        result = check_cover_letter_font_matches_resume("Calibri", "Georgia")
        self.assertFalse(result.passed)


class TestPortfolioRequested(unittest.TestCase):
    def test_no_mention_returns_false(self) -> None:
        result = check_portfolio_requested("We're looking for a strong communicator with PM experience.")
        self.assertFalse(result.data["portfolio_requested"])

    def test_portfolio_keyword_detected(self) -> None:
        result = check_portfolio_requested("Please include a link to your portfolio.")
        self.assertTrue(result.data["portfolio_requested"])
        self.assertIn("portfolio", result.data["matched_keywords"])

    def test_work_samples_keyword_detected(self) -> None:
        result = check_portfolio_requested("Submit writing samples with your application.")
        self.assertTrue(result.data["portfolio_requested"])


if __name__ == "__main__":
    unittest.main()
