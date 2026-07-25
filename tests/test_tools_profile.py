import unittest

from app.session import Fact, Finding, Session
from app.tools.profile import (
    apply_dismissed_findings,
    check_profile_integrity,
    export_iris_profile,
    import_iris_profile,
)


class TestProfileRoundTrip(unittest.TestCase):
    def setUp(self) -> None:
        self.session = Session(session_id="s", user_id="u", master_fingerprint="abc123")
        self.session.registry["F-001"] = Fact(id="F-001", type="skill", value="Python", statement="Uses Python.")
        self.session.findings.append(
            Finding(id="f1", tool_id="T-3.14", severity="Low", issue="Self-annotation.", fix="Cut it.", content_signature="sig123", dismissed=True)
        )

    def test_export_produces_valid_markdown(self) -> None:
        result = export_iris_profile(session=self.session)
        self.assertTrue(result.passed)
        markdown = result.data["profile_markdown"]
        self.assertIn("Checksum:", markdown)
        self.assertIn("```json", markdown)

    def test_exported_profile_passes_integrity_check(self) -> None:
        exported = export_iris_profile(session=self.session)
        integrity = check_profile_integrity(exported.data["profile_markdown"])
        self.assertTrue(integrity.passed)

    def test_tampered_profile_fails_integrity_check(self) -> None:
        exported = export_iris_profile(session=self.session)
        tampered = exported.data["profile_markdown"].replace('"Python"', '"Rust"')
        integrity = check_profile_integrity(tampered)
        self.assertFalse(integrity.passed)
        self.assertEqual(integrity.findings[0]["severity"], "Critical")

    def test_truncated_profile_fails_integrity_check(self) -> None:
        exported = export_iris_profile(session=self.session)
        truncated = exported.data["profile_markdown"][: len(exported.data["profile_markdown"]) // 2]
        integrity = check_profile_integrity(truncated)
        self.assertFalse(integrity.passed)

    def test_full_round_trip_imports_correctly(self) -> None:
        exported = export_iris_profile(session=self.session)
        integrity = check_profile_integrity(exported.data["profile_markdown"])
        imported = import_iris_profile(integrity.data["json_body"])
        self.assertTrue(imported.passed)
        payload = imported.data["payload"]
        self.assertEqual(payload["master_fingerprint"], "abc123")
        self.assertEqual(len(payload["registry"]), 1)
        self.assertEqual(payload["registry"][0]["value"], "Python")

    def test_import_rejects_wrong_version(self) -> None:
        result = import_iris_profile('{"version": 999, "registry": [], "dismissed_findings": []}')
        self.assertFalse(result.passed)

    def test_import_rejects_missing_keys(self) -> None:
        result = import_iris_profile('{"version": 1}')
        self.assertFalse(result.passed)

    def test_import_rejects_malformed_json(self) -> None:
        result = import_iris_profile("{not valid json")
        self.assertFalse(result.passed)


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
