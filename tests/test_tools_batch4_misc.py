import unittest

from app.tools.cover_letter import (
    check_cover_letter_paragraph_count,
    check_cover_letter_word_count,
    route_cover_letter_artifact_type,
)
from app.tools.intake import check_missing_required_sections


class TestCoverLetterParagraphCount(unittest.TestCase):
    def test_four_paragraphs_passes(self) -> None:
        letter = "One.\n\nTwo.\n\nThree.\n\nFour."
        result = check_cover_letter_paragraph_count(letter)
        self.assertTrue(result.passed)

    def test_three_paragraphs_fails(self) -> None:
        letter = "One.\n\nTwo.\n\nThree."
        result = check_cover_letter_paragraph_count(letter)
        self.assertFalse(result.passed)
        self.assertEqual(result.data["paragraph_count"], 3)

    def test_five_paragraphs_fails(self) -> None:
        letter = "One.\n\nTwo.\n\nThree.\n\nFour.\n\nFive."
        result = check_cover_letter_paragraph_count(letter)
        self.assertFalse(result.passed)


class TestCoverLetterWordCount(unittest.TestCase):
    def test_in_range_passes(self) -> None:
        letter = " ".join(["word"] * 300)
        result = check_cover_letter_word_count(letter)
        self.assertTrue(result.passed)

    def test_too_short_fails(self) -> None:
        letter = " ".join(["word"] * 100)
        result = check_cover_letter_word_count(letter)
        self.assertFalse(result.passed)

    def test_too_long_fails(self) -> None:
        letter = " ".join(["word"] * 500)
        result = check_cover_letter_word_count(letter)
        self.assertFalse(result.passed)


class TestRouteCoverLetterArtifactType(unittest.TestCase):
    def test_with_jd_routes_to_cover_letter(self) -> None:
        result = route_cover_letter_artifact_type(has_job_description=True)
        self.assertEqual(result.data["artifact_type"], "cover_letter")

    def test_without_jd_routes_to_letter_of_interest(self) -> None:
        result = route_cover_letter_artifact_type(has_job_description=False)
        self.assertEqual(result.data["artifact_type"], "letter_of_interest")


class TestMissingRequiredSections(unittest.TestCase):
    def test_all_present_passes(self) -> None:
        result = check_missing_required_sections(["NAME", "HEADLINE", "CONTACT", "SUMMARY", "SKILLS", "EXPERIENCE"])
        self.assertTrue(result.passed)

    def test_missing_section_is_critical(self) -> None:
        result = check_missing_required_sections(["NAME", "CONTACT", "SKILLS", "EXPERIENCE"])
        self.assertFalse(result.passed)
        self.assertIn("HEADLINE", result.data["missing_sections"])
        self.assertIn("SUMMARY", result.data["missing_sections"])

    def test_projects_never_required(self) -> None:
        result = check_missing_required_sections(["NAME", "HEADLINE", "CONTACT", "SUMMARY", "SKILLS", "EXPERIENCE"])
        self.assertTrue(result.passed)  # PROJECTS absent, still passes


if __name__ == "__main__":
    unittest.main()
