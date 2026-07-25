import unittest

from app.session import Finding, Session
from app.tools.audit import compute_content_signature, filter_carried_forward_findings


class TestComputeContentSignature(unittest.TestCase):
    def test_same_input_same_signature(self) -> None:
        a = compute_content_signature("T-3.1", "1 em dash found.")
        b = compute_content_signature("T-3.1", "1 em dash found.")
        self.assertEqual(a, b)

    def test_different_issue_text_different_signature(self) -> None:
        a = compute_content_signature("T-3.1", "1 em dash found.")
        b = compute_content_signature("T-3.1", "2 em dashes found.")
        self.assertNotEqual(a, b)

    def test_different_tool_id_different_signature(self) -> None:
        a = compute_content_signature("T-3.1", "same text")
        b = compute_content_signature("T-3.3", "same text")
        self.assertNotEqual(a, b)


class TestFilterCarriedForwardFindings(unittest.TestCase):
    def setUp(self) -> None:
        self.session = Session(session_id="s", user_id="u")

    def test_new_finding_surfaces(self) -> None:
        result = filter_carried_forward_findings(
            [{"tool_id": "T-3.1", "issue": "1 em dash found.", "severity": "Critical", "fix": "Replace it."}],
            session=self.session,
        )
        self.assertEqual(len(result.data["surfaced"]), 1)
        self.assertEqual(len(result.data["already_dismissed"]), 0)

    def test_dismissed_finding_with_matching_signature_stays_dismissed(self) -> None:
        sig = compute_content_signature("T-3.14", "Self-annotation in bullet 2.")
        self.session.findings.append(
            Finding(
                id="f1",
                tool_id="T-3.14",
                severity="Low",
                issue="Self-annotation in bullet 2.",
                fix="Cut it.",
                content_signature=sig,
                dismissed=True,
            )
        )
        result = filter_carried_forward_findings(
            [{"tool_id": "T-3.14", "issue": "Self-annotation in bullet 2.", "severity": "Low", "fix": "Cut it."}],
            session=self.session,
        )
        self.assertEqual(len(result.data["surfaced"]), 0)
        self.assertEqual(len(result.data["already_dismissed"]), 1)

    def test_revised_text_produces_new_signature_and_resurfaces(self) -> None:
        old_sig = compute_content_signature("T-3.14", "Self-annotation in bullet 2.")
        self.session.findings.append(
            Finding(
                id="f1",
                tool_id="T-3.14",
                severity="Low",
                issue="Self-annotation in bullet 2.",
                fix="Cut it.",
                content_signature=old_sig,
                dismissed=True,
            )
        )
        # Bullet 2 was revised; the finding text is now different.
        result = filter_carried_forward_findings(
            [{"tool_id": "T-3.14", "issue": "Self-annotation in bullet 3.", "severity": "Low", "fix": "Cut it."}],
            session=self.session,
        )
        self.assertEqual(len(result.data["surfaced"]), 1)
        self.assertEqual(len(result.data["already_dismissed"]), 0)

    def test_non_dismissed_finding_does_not_suppress_carry_forward(self) -> None:
        sig = compute_content_signature("T-3.1", "1 em dash found.")
        self.session.findings.append(
            Finding(
                id="f1", tool_id="T-3.1", severity="Critical", issue="1 em dash found.", fix="Replace it.",
                content_signature=sig, dismissed=False,
            )
        )
        result = filter_carried_forward_findings(
            [{"tool_id": "T-3.1", "issue": "1 em dash found.", "severity": "Critical", "fix": "Replace it."}],
            session=self.session,
        )
        self.assertEqual(len(result.data["surfaced"]), 1)


if __name__ == "__main__":
    unittest.main()
