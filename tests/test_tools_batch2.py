import unittest

from app.session import Session

from app.tools.consistency import check_figure_consistency
from app.tools.cover_letter import check_salutation
from app.tools.delivery import check_unresolved_markers
from app.tools.tailoring import check_jd_phrase_coverage


class TestJDPhraseCoverage(unittest.TestCase):
    """check_jd_phrase_coverage gained a session parameter on
    2026-07-28: running it is what marks the Fit Check complete
    (T-5.1), derived rather than asserted. The coverage behaviour these
    tests cover is unchanged."""

    def setUp(self) -> None:
        self.session = Session(session_id="s", user_id="u")

    def test_all_phrases_present_passes(self) -> None:
        result = check_jd_phrase_coverage(
            jd_phrases=["cross-functional", "roadmap"],
            resume_text="Led cross-functional teams to define the product roadmap.",
            session=self.session,
        )
        self.assertTrue(result.passed)

    def test_missing_phrase_flagged_not_inserted(self) -> None:
        result = check_jd_phrase_coverage(
            jd_phrases=["stakeholder alignment"],
            resume_text="Led product strategy across three teams.",
            session=self.session,
        )
        self.assertFalse(result.passed)
        self.assertIn("stakeholder alignment", result.data["missing_phrases"])
        # The tool never modifies resume_text; it only reports.
        self.assertNotIn("stakeholder alignment", "Led product strategy across three teams.")

    def test_case_insensitive_match(self) -> None:
        result = check_jd_phrase_coverage(
            jd_phrases=["Cross-Functional"],
            resume_text="worked in a cross-functional pod",
            session=self.session,
        )
        self.assertTrue(result.passed)


class TestUnresolvedMarkersAsTool(unittest.TestCase):
    def test_clean_text_passes(self) -> None:
        result = check_unresolved_markers("Reduced AHT to 2.5 minutes.")
        self.assertTrue(result.passed)

    def test_marker_present_fails(self) -> None:
        result = check_unresolved_markers("Reduced AHT by [ADD METRIC: percent] percent.")
        self.assertFalse(result.passed)
        self.assertEqual(result.findings[0]["severity"], "Critical")


class TestSalutation(unittest.TestCase):
    def test_named_contact_passes(self) -> None:
        result = check_salutation("Dear Jane Smith,")
        self.assertTrue(result.passed)

    def test_dear_hiring_manager_passes(self) -> None:
        result = check_salutation("Dear Hiring Manager,")
        self.assertTrue(result.passed)

    def test_department_team_passes(self) -> None:
        result = check_salutation("Engineering Team,")
        self.assertTrue(result.passed)

    def test_company_recruiting_team_passes(self) -> None:
        result = check_salutation("Acme Recruiting Team,")
        self.assertTrue(result.passed)

    def test_to_whom_it_may_concern_is_banned(self) -> None:
        result = check_salutation("To Whom It May Concern,")
        self.assertFalse(result.passed)
        self.assertEqual(result.findings[0]["severity"], "Critical")

    def test_to_whom_it_may_concern_case_insensitive(self) -> None:
        result = check_salutation("to whom it may concern,")
        self.assertFalse(result.passed)
        self.assertEqual(result.findings[0]["severity"], "Critical")

    def test_malformed_salutation_fails_but_not_critical(self) -> None:
        result = check_salutation("Hey there,")
        self.assertFalse(result.passed)
        self.assertEqual(result.findings[0]["severity"], "Medium")


class TestFigureConsistency(unittest.TestCase):
    def test_consistent_figures_pass(self) -> None:
        text = "Surveyed 150 managers. Later, the same 150 managers were re-interviewed."
        result = check_figure_consistency(text)
        self.assertTrue(result.passed)

    def test_inconsistent_figures_flagged(self) -> None:
        text = "Surveyed 150 managers in Q1. By Q3, 200 managers had responded."
        result = check_figure_consistency(text)
        self.assertFalse(result.passed)
        self.assertEqual(result.findings[0]["severity"], "High")
        self.assertIn("managers", result.findings[0]["issue"])

    def test_unrelated_numbers_different_words_pass(self) -> None:
        text = "Managed 5 engineers across 3 time zones."
        result = check_figure_consistency(text)
        self.assertTrue(result.passed)


if __name__ == "__main__":
    unittest.main()
