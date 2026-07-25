import unittest

from app.tools.security import check_confidential_term_leak


class TestConfidentialTermLeak(unittest.TestCase):
    def test_clean_text_passes(self) -> None:
        result = check_confidential_term_leak(
            "Led migration of the billing service.", blocked_terms=["Project Nightingale"]
        )
        self.assertTrue(result.passed)

    def test_leaked_term_is_critical(self) -> None:
        result = check_confidential_term_leak(
            "Led Project Nightingale to completion.", blocked_terms=["Project Nightingale"]
        )
        self.assertFalse(result.passed)
        self.assertEqual(result.findings[0]["severity"], "Critical")

    def test_allowlisted_term_does_not_fail(self) -> None:
        result = check_confidential_term_leak(
            "Project Oxygen was a widely publicized initiative.",
            blocked_terms=["Project Oxygen"],
            allowlist=["Project Oxygen"],
        )
        self.assertTrue(result.passed)

    def test_case_insensitive_match(self) -> None:
        result = check_confidential_term_leak(
            "worked on project nightingale", blocked_terms=["Project Nightingale"]
        )
        self.assertFalse(result.passed)

    def test_multiple_blocked_terms_all_checked(self) -> None:
        result = check_confidential_term_leak(
            "Project Nightingale and Project Falcon both shipped.",
            blocked_terms=["Project Nightingale", "Project Falcon"],
        )
        self.assertFalse(result.passed)
        self.assertEqual(len(result.findings), 2)


if __name__ == "__main__":
    unittest.main()
