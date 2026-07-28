import unittest

from app.session import Finding, Session
from app.tools.foundational_build import check_bold_lead_structure, get_open_audit_findings_for_section


class TestBoldLeadStructure(unittest.TestCase):
    def test_in_range_passes(self) -> None:
        result = check_bold_lead_structure("Led cross-functional migration")
        self.assertTrue(result.passed)
        self.assertEqual(result.data["word_count"], 3)

    def test_too_short_fails(self) -> None:
        result = check_bold_lead_structure("Led it")
        self.assertFalse(result.passed)

    def test_too_long_fails(self) -> None:
        result = check_bold_lead_structure("Led the entire cross functional platform migration effort")
        self.assertFalse(result.passed)

    def test_six_words_passes(self) -> None:
        result = check_bold_lead_structure("Led a six word bold lead")
        self.assertTrue(result.passed)


class TestGetOpenAuditFindingsForSection(unittest.TestCase):
    def setUp(self) -> None:
        self.session = Session(session_id="s", user_id="u")

    def test_no_findings_passes(self) -> None:
        result = get_open_audit_findings_for_section("EXPERIENCE", session=self.session)
        self.assertTrue(result.passed)
        self.assertEqual(result.data["open_count"], 0)

    def test_matching_open_finding_surfaces(self) -> None:
        self.session.findings.append(
            Finding(id="f1", tool_id="T-1.1", severity="Medium", issue="Content gap in Experience.", fix="Add detail.", section="EXPERIENCE")
        )
        result = get_open_audit_findings_for_section("EXPERIENCE", session=self.session)
        self.assertFalse(result.passed)
        self.assertEqual(result.data["open_count"], 1)

    def test_dismissed_finding_does_not_surface(self) -> None:
        self.session.findings.append(
            Finding(id="f1", tool_id="T-1.1", severity="Medium", issue="x", fix="y", section="EXPERIENCE", dismissed=True)
        )
        result = get_open_audit_findings_for_section("EXPERIENCE", session=self.session)
        self.assertTrue(result.passed)

    def test_finding_for_different_section_not_returned(self) -> None:
        self.session.findings.append(
            Finding(id="f1", tool_id="T-1.1", severity="Medium", issue="x", fix="y", section="EDUCATION")
        )
        result = get_open_audit_findings_for_section("EXPERIENCE", session=self.session)
        self.assertTrue(result.passed)


if __name__ == "__main__":
    unittest.main()
