import unittest

from app.tools.formatting import check_filename_pattern, check_section_header


class TestSectionHeader(unittest.TestCase):
    def test_canonical_header_passes(self) -> None:
        result = check_section_header("Experience")
        self.assertTrue(result.passed)

    def test_common_synonym_passes(self) -> None:
        result = check_section_header("Professional Experience")
        self.assertTrue(result.passed)

    def test_case_insensitive(self) -> None:
        result = check_section_header("SKILLS")
        self.assertTrue(result.passed)

    def test_unconventional_header_fails(self) -> None:
        result = check_section_header("My Journey")
        self.assertFalse(result.passed)
        self.assertEqual(result.findings[0]["severity"], "Medium")


class TestFilenamePattern(unittest.TestCase):
    def test_valid_tailored_resume_passes(self) -> None:
        result = check_filename_pattern(
            "Kenitzer_Josh_Resume_Acme_SrPM_v1.docx", artifact_type="tailored_resume"
        )
        self.assertTrue(result.passed)

    def test_tailored_resume_missing_role_fails(self) -> None:
        result = check_filename_pattern(
            "Kenitzer_Josh_Resume_Acme_v1.docx", artifact_type="tailored_resume"
        )
        self.assertFalse(result.passed)

    def test_valid_cover_letter_passes(self) -> None:
        result = check_filename_pattern(
            "Kenitzer_Josh_CoverLetter_Acme_SrPM_v1.docx", artifact_type="cover_letter"
        )
        self.assertTrue(result.passed)

    def test_valid_master_passes(self) -> None:
        result = check_filename_pattern(
            "Kenitzer_Josh_Resume_Master_2026-07-24.docx", artifact_type="master"
        )
        self.assertTrue(result.passed)

    def test_master_with_version_suffix_passes(self) -> None:
        result = check_filename_pattern(
            "Kenitzer_Josh_Resume_Master_2026-07-24_v2.docx", artifact_type="master"
        )
        self.assertTrue(result.passed)

    def test_master_pattern_used_for_tailored_file_fails(self) -> None:
        result = check_filename_pattern(
            "Kenitzer_Josh_Resume_Master_2026-07-24.docx", artifact_type="tailored_resume"
        )
        self.assertFalse(result.passed)

    def test_unknown_artifact_type_fails(self) -> None:
        result = check_filename_pattern("anything.docx", artifact_type="banner")
        self.assertFalse(result.passed)


if __name__ == "__main__":
    unittest.main()
