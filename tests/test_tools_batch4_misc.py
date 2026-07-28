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


class TestSignatureIsNotABodyParagraph(unittest.TestCase):
    """Regression coverage for a live defect (2026-07-28). Counting every
    blank-line block made a signature the fifth paragraph, so T-7.1
    failed on a correct letter, and the model resolved the failure by
    deleting the sender's name. A cover letter shipped with no signature
    and only the user caught it.

    The paragraph rule was always about the four BODY paragraphs (spec
    Phase 7). Salutation and signature are structure around them."""

    BODY = (
        "Dear Hiring Manager,\n\n"
        "Opening hook referencing the role.\n\n"
        "Core capability argument with quantified evidence.\n\n"
        "Company alignment carrying the honest gap.\n\n"
        "Closing that invites a conversation."
    )

    def test_sign_off_and_name_together(self) -> None:
        result = check_cover_letter_paragraph_count(self.BODY + "\n\nSincerely,\nJoshua Kenitzer")
        self.assertTrue(result.passed)
        self.assertEqual(result.data["paragraph_count"], 4)
        self.assertTrue(result.data["has_signature"])

    def test_bare_name_with_no_sign_off(self) -> None:
        """The shape seen live: just the name on its own line."""
        result = check_cover_letter_paragraph_count(self.BODY + "\n\nJoshua Kenitzer")
        self.assertTrue(result.passed)
        self.assertTrue(result.data["has_signature"])

    def test_sign_off_and_name_as_separate_blocks(self) -> None:
        result = check_cover_letter_paragraph_count(self.BODY + "\n\nSincerely,\n\nJoshua Kenitzer")
        self.assertTrue(result.passed)
        self.assertTrue(result.data["has_signature"])

    def test_salutation_is_not_counted(self) -> None:
        result = check_cover_letter_paragraph_count(self.BODY)
        self.assertTrue(result.passed)
        self.assertTrue(result.data["has_salutation"])

    def test_a_genuinely_short_letter_still_fails(self) -> None:
        """The check must not become permissive: excluding structure is
        not the same as excusing a letter from the rule."""
        result = check_cover_letter_paragraph_count(
            "Dear Hiring Manager,\n\nOne.\n\nTwo.\n\nSincerely,\nJoshua Kenitzer"
        )
        self.assertFalse(result.passed)
        self.assertEqual(result.data["paragraph_count"], 2)

    def test_a_genuinely_long_letter_still_fails(self) -> None:
        result = check_cover_letter_paragraph_count(
            "Dear Hiring Manager,\n\nOne.\n\nTwo.\n\nThree.\n\nFour.\n\nFive.\n\nSincerely,\nJoshua Kenitzer"
        )
        self.assertFalse(result.passed)
        self.assertEqual(result.data["paragraph_count"], 5)

    def test_a_short_final_paragraph_is_not_mistaken_for_a_name(self) -> None:
        """A real paragraph ends in sentence punctuation; a signature
        does not. That is the whole distinction, so it has to hold for a
        genuinely brief closing line."""
        result = check_cover_letter_paragraph_count(
            "Dear Hiring Manager,\n\nOne.\n\nTwo.\n\nThree.\n\nI look forward to it."
        )
        self.assertTrue(result.passed)
        self.assertFalse(result.data["has_signature"])


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
