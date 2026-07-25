import unittest

from app.tools.slop import check_user_defined_terms, check_vague_metrics


class TestUserDefinedTerms(unittest.TestCase):
    def test_no_match_passes(self) -> None:
        result = check_user_defined_terms("Led the onboarding redesign.", terms=["Project Falcon"])
        self.assertTrue(result.passed)

    def test_match_fails(self) -> None:
        result = check_user_defined_terms(
            "Led the Project Falcon onboarding redesign.", terms=["Project Falcon"]
        )
        self.assertFalse(result.passed)
        self.assertEqual(result.findings[0]["severity"], "Medium")

    def test_case_insensitive(self) -> None:
        result = check_user_defined_terms("Worked on project falcon.", terms=["Project Falcon"])
        self.assertFalse(result.passed)

    def test_empty_term_list_passes(self) -> None:
        result = check_user_defined_terms("Anything at all.", terms=[])
        self.assertTrue(result.passed)


class TestVagueMetrics(unittest.TestCase):
    def test_quantifier_with_nearby_number_passes(self) -> None:
        result = check_vague_metrics("Significantly reduced churn by 18 percent in six months.")
        self.assertTrue(result.passed)

    def test_quantifier_with_no_number_fails(self) -> None:
        result = check_vague_metrics("Significantly improved team morale and engagement.")
        self.assertFalse(result.passed)
        self.assertEqual(result.findings[0]["severity"], "Medium")

    def test_number_outside_window_still_fails(self) -> None:
        text = "Significantly " + " ".join(["filler"] * 20) + " 42 percent."
        result = check_vague_metrics(text, window_words=3)
        self.assertFalse(result.passed)

    def test_no_quantifiers_passes(self) -> None:
        result = check_vague_metrics("Reduced onboarding time from two months to two weeks.")
        self.assertTrue(result.passed)


if __name__ == "__main__":
    unittest.main()
