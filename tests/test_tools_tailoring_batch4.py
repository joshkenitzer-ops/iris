import unittest

from app.session import Session
from app.tools.tailoring import get_fit_check_gaps_for_cover_letter, replace_internal_names


class TestReplaceInternalNames(unittest.TestCase):
    def test_term_replaced(self) -> None:
        result = replace_internal_names(
            "Led Project Falcon to launch.", term_replacements={"Project Falcon": "an internal platform initiative"}
        )
        self.assertTrue(result.passed)
        self.assertIn("an internal platform initiative", result.data["replaced_text"])
        self.assertNotIn("Falcon", result.data["replaced_text"])

    def test_case_insensitive_replacement(self) -> None:
        result = replace_internal_names(
            "worked on project falcon", term_replacements={"Project Falcon": "an internal initiative"}
        )
        self.assertTrue(result.passed)

    def test_longest_term_replaced_first(self) -> None:
        result = replace_internal_names(
            "Project Falcon Advanced shipped.",
            term_replacements={"Project Falcon": "a platform", "Project Falcon Advanced": "an advanced platform"},
        )
        self.assertTrue(result.passed)
        self.assertNotIn("Falcon", result.data["replaced_text"])

    def test_no_terms_present_passes_unchanged(self) -> None:
        result = replace_internal_names("Led onboarding redesign.", term_replacements={"Project Falcon": "x"})
        self.assertTrue(result.passed)
        self.assertEqual(result.data["replaced_text"], "Led onboarding redesign.")


class TestGetFitCheckGapsForCoverLetter(unittest.TestCase):
    def test_no_gaps_returns_empty_list(self) -> None:
        session = Session(session_id="s", user_id="u")
        result = get_fit_check_gaps_for_cover_letter(session=session)
        self.assertEqual(result.data["gaps"], [])

    def test_stored_gaps_are_returned(self) -> None:
        session = Session(session_id="s", user_id="u")
        session.fit_check_gaps = ["No direct experience with regulated industries."]
        result = get_fit_check_gaps_for_cover_letter(session=session)
        self.assertEqual(len(result.data["gaps"]), 1)


if __name__ == "__main__":
    unittest.main()
