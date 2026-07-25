import unittest

from app.tools.verification import check_primary_source_support


class TestCheckPrimarySourceSupport(unittest.TestCase):
    def test_claim_fully_supported_passes(self) -> None:
        result = check_primary_source_support(
            claim_text="Reduced AHT to 2.5 minutes across the Fiber team.",
            source_text="The Fiber team's AHT dropped to 2.5 minutes after the change.",
        )
        self.assertTrue(result.passed)

    def test_missing_token_flagged_not_resolved(self) -> None:
        result = check_primary_source_support(
            claim_text="Led a team of 12 engineers across Southeast Asia.",
            source_text="Led a team of engineers on several projects.",
        )
        self.assertFalse(result.passed)
        self.assertEqual(result.findings[0]["severity"], "Medium")
        self.assertIn("Treat as suspect and ask", result.findings[0]["fix"])

    def test_number_token_checked(self) -> None:
        result = check_primary_source_support(
            claim_text="Surveyed 2,680 respondents.", source_text="No survey numbers mentioned here."
        )
        self.assertFalse(result.passed)
        self.assertIn("2,680", result.data["missing_tokens"])

    def test_no_distinctive_tokens_passes_trivially(self) -> None:
        result = check_primary_source_support(claim_text="did some work", source_text="unrelated text entirely")
        self.assertTrue(result.passed)


if __name__ == "__main__":
    unittest.main()
