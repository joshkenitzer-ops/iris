import unittest

from app.config import BULLET_WORD_LIMIT_DEFAULT
from app.tools.formatting import check_bullet_word_limit, check_date_format


class TestDateFormat(unittest.TestCase):
    def test_valid_range_passes(self) -> None:
        result = check_date_format("Mar 2022 - Jul 2025")
        self.assertTrue(result.passed)

    def test_present_is_rejected(self) -> None:
        result = check_date_format("Mar 2022 - Present")
        self.assertFalse(result.passed)
        self.assertEqual(result.findings[0]["severity"], "Critical")

    def test_year_only_is_rejected(self) -> None:
        result = check_date_format("2022 - 2025")
        self.assertFalse(result.passed)

    def test_malformed_text_is_rejected(self) -> None:
        result = check_date_format("March 2022 to July 2025")
        self.assertFalse(result.passed)


class TestBulletWordLimit(unittest.TestCase):
    def test_short_bullet_passes(self) -> None:
        result = check_bullet_word_limit("Led migration of the billing service to the new platform.")
        self.assertTrue(result.passed)

    def test_over_limit_bullet_flags_low_severity(self) -> None:
        long_bullet = " ".join(["word"] * (BULLET_WORD_LIMIT_DEFAULT + 5))
        result = check_bullet_word_limit(long_bullet)
        self.assertFalse(result.passed)
        self.assertEqual(result.findings[0]["severity"], "Low")
        self.assertEqual(result.data["word_count"], BULLET_WORD_LIMIT_DEFAULT + 5)

    def test_exactly_at_limit_passes(self) -> None:
        exact_bullet = " ".join(["word"] * BULLET_WORD_LIMIT_DEFAULT)
        result = check_bullet_word_limit(exact_bullet)
        self.assertTrue(result.passed)


if __name__ == "__main__":
    unittest.main()
