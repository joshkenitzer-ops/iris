import base64
import unittest

from app.session import Fact, Finding, Session
from app.tools.profile import (
    apply_dismissed_findings,
    check_profile_integrity,
    export_iris_profile,
    import_iris_profile,
)


def _exported_markdown(session: Session) -> str:
    """Exports a profile and retrieves the actual markdown content
    from where it now lives: in the session's rendered_files store,
    not in the tool result's data dict (which now holds file_id /
    filename / checksum for the frontend's download mechanism)."""
    result = export_iris_profile(filename="Test_User_IrisProfile.md", session=session)
    assert result.passed
    rendered = session.get_rendered_file(result.data["file_id"])
    assert rendered is not None
    return base64.b64decode(rendered.data_base64).decode("utf-8")


class TestProfileExport(unittest.TestCase):
    def setUp(self) -> None:
        self.session = Session(session_id="s", user_id="u", master_fingerprint="abc123")
        self.session.registry["F-001"] = Fact(id="F-001", type="skill", value="Python", statement="Uses Python.")
        self.session.findings.append(
            Finding(id="f1", tool_id="T-3.14", severity="Low", issue="Self-annotation.", fix="Cut it.", content_signature="sig123", dismissed=True)
        )

    def test_export_returns_file_id_filename_checksum(self) -> None:
        result = export_iris_profile(filename="Test_User_IrisProfile.md", session=self.session)
        self.assertTrue(result.passed)
        self.assertIn("file_id", result.data)
        self.assertIn("filename", result.data)
        self.assertIn("checksum", result.data)
        self.assertEqual(result.data["filename"], "Test_User_IrisProfile.md")

    def test_export_stores_file_on_session(self) -> None:
        result = export_iris_profile(filename="Test_User_IrisProfile.md", session=self.session)
        rendered = self.session.get_rendered_file(result.data["file_id"])
        self.assertIsNotNone(rendered)
        self.assertEqual(rendered.filename, "Test_User_IrisProfile.md")
        self.assertEqual(rendered.content_type, "text/markdown")

    def test_exported_markdown_contains_expected_structure(self) -> None:
        markdown = _exported_markdown(self.session)
        self.assertIn("Checksum:", markdown)
        self.assertIn("```json", markdown)

    def test_exported_markdown_passes_integrity_check(self) -> None:
        markdown = _exported_markdown(self.session)
        integrity = check_profile_integrity(markdown)
        self.assertTrue(integrity.passed)

    def test_tampered_markdown_fails_integrity_check(self) -> None:
        markdown = _exported_markdown(self.session)
        tampered = markdown.replace('"Python"', '"Rust"')
        self.assertFalse(check_profile_integrity(tampered).passed)
        self.assertEqual(check_profile_integrity(tampered).findings[0]["severity"], "Critical")

    def test_truncated_markdown_fails_integrity_check(self) -> None:
        markdown = _exported_markdown(self.session)
        truncated = markdown[: len(markdown) // 2]
        self.assertFalse(check_profile_integrity(truncated).passed)

    def test_full_round_trip_imports_correctly(self) -> None:
        markdown = _exported_markdown(self.session)
        integrity = check_profile_integrity(markdown)
        self.assertTrue(integrity.passed)
        imported = import_iris_profile(integrity.data["json_body"])
        self.assertTrue(imported.passed)
        payload = imported.data["payload"]
        self.assertEqual(payload["master_fingerprint"], "abc123")
        self.assertEqual(len(payload["registry"]), 1)
        self.assertEqual(payload["registry"][0]["value"], "Python")

    def test_import_rejects_wrong_version(self) -> None:
        self.assertFalse(import_iris_profile('{"version": 999, "registry": [], "dismissed_findings": []}').passed)

    def test_import_rejects_missing_keys(self) -> None:
        self.assertFalse(import_iris_profile('{"version": 1}').passed)

    def test_import_rejects_malformed_json(self) -> None:
        self.assertFalse(import_iris_profile("{not valid json").passed)


class TestApplyDismissedFindings(unittest.TestCase):
    def test_matching_finding_marked_dismissed(self) -> None:
        session = Session(session_id="s", user_id="u")
        session.findings.append(
            Finding(id="f1", tool_id="T-3.14", severity="Low", issue="Self-annotation.", fix="Cut it.", content_signature="sig-x")
        )
        result = apply_dismissed_findings(
            [{"tool_id": "T-3.14", "issue": "Self-annotation.", "content_signature": "sig-x"}], session=session
        )
        self.assertTrue(result.passed)
        self.assertTrue(session.findings[0].dismissed)

    def test_no_matching_finding_creates_placeholder(self) -> None:
        session = Session(session_id="s", user_id="u")
        result = apply_dismissed_findings(
            [{"tool_id": "T-3.14", "issue": "Old finding no longer present.", "content_signature": "sig-y"}],
            session=session,
        )
        self.assertTrue(result.passed)
        self.assertEqual(len(session.findings), 1)
        self.assertTrue(session.findings[0].dismissed)

    def test_missing_signature_is_computed(self) -> None:
        session = Session(session_id="s", user_id="u")
        result = apply_dismissed_findings(
            [{"tool_id": "T-3.14", "issue": "No explicit signature given."}], session=session
        )
        self.assertTrue(result.passed)
        self.assertIsNotNone(session.findings[0].content_signature)


if __name__ == "__main__":
    unittest.main()
