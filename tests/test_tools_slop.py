import unittest

from app.tools.slop import check_banned_vocabulary, check_em_dash


class TestEmDash(unittest.TestCase):
    def test_clean_text_passes(self) -> None:
        result = check_em_dash("Led a team of five engineers.")
        self.assertTrue(result.passed)
        self.assertEqual(result.findings, [])

    def test_single_em_dash_fails(self) -> None:
        result = check_em_dash("Led a team\u2014five engineers.")
        self.assertFalse(result.passed)
        self.assertEqual(len(result.findings), 1)
        self.assertEqual(result.findings[0]["severity"], "Critical")

    def test_counts_multiple_occurrences(self) -> None:
        result = check_em_dash("One\u2014two\u2014three\u2014four.")
        self.assertFalse(result.passed)
        self.assertIn("3 em dash", result.findings[0]["issue"])

    def test_regular_hyphen_is_fine(self) -> None:
        result = check_em_dash("Mar 2022 - Jul 2025, a well-known role.")
        self.assertTrue(result.passed)


class TestBannedVocabulary(unittest.TestCase):
    def test_clean_text_passes(self) -> None:
        result = check_banned_vocabulary("Cut onboarding time from two months to two weeks.")
        self.assertTrue(result.passed)

    def test_always_flagged_term_fires_on_single_use(self) -> None:
        result = check_banned_vocabulary("Seamlessly integrated the new pipeline.")
        self.assertFalse(result.passed)
        self.assertTrue(any("seamlessly" in f["issue"] for f in result.findings))

    def test_frequency_gated_term_below_threshold_passes(self) -> None:
        # Threshold is 2 by default; a single, ordinary use should not fire.
        result = check_banned_vocabulary("This effectively cut onboarding time in half.")
        self.assertTrue(result.passed)

    def test_frequency_gated_term_above_threshold_fires(self) -> None:
        text = "This effectively cut time. It also effectively reduced cost, effectively."
        result = check_banned_vocabulary(text)
        self.assertFalse(result.passed)
        self.assertTrue(any("effectively" in f["issue"] for f in result.findings))

    def test_frequency_counts_reported_even_when_passing(self) -> None:
        result = check_banned_vocabulary("This effectively cut onboarding time.")
        self.assertIn("effectively", result.data["frequency_gated_counts"])
        self.assertEqual(result.data["frequency_gated_counts"]["effectively"], 1)


if __name__ == "__main__":
    unittest.main()
