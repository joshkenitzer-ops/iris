import unittest

from app.session import Session
from app.tools.slop_advanced import (
    nominate_repeated_opener_candidates,
    nominate_tense_inconsistency_candidates,
)


def _session_with_cached_text(text: str):
    """Mirrors what ingest_document does after a successful extraction:
    stash the raw text on the attachment so later HYBRID checks can
    resolve it by attachment_id instead of the model pasting it back."""
    session = Session(session_id="s", user_id="u")
    attachment = session.add_attachment(filename="resume.docx", file_type="docx", data=b"")
    attachment.extracted_text = text
    return session, attachment.id


class TestNominateRepeatedOpenerCandidates(unittest.TestCase):
    """T-3.18. Zero prior coverage for this tool — also the regression
    surface for the latency fix: the model must never have to paste the
    whole uploaded document back in as `text` when `attachment_id` will
    do, the same principle already applied to run_batch_checks."""

    def test_explicit_text_still_works_unchanged(self) -> None:
        text = "Led the team. Led the rollout. Led the migration. Shipped the feature."
        result = nominate_repeated_opener_candidates(text=text, session=None)
        self.assertFalse(result.passed)
        self.assertEqual(len(result.data["runs"]), 1)
        self.assertEqual(result.data["runs"][0]["opener"], "led")

    def test_clean_text_passes(self) -> None:
        text = "Led the rollout. Shipped the feature. Managed the migration."
        result = nominate_repeated_opener_candidates(text=text, session=None)
        self.assertTrue(result.passed)

    def test_attachment_id_resolves_cached_text(self) -> None:
        text = "Led the team. Led the rollout. Led the migration."
        session, attachment_id = _session_with_cached_text(text)
        result = nominate_repeated_opener_candidates(attachment_id=attachment_id, session=session)
        self.assertFalse(result.passed)
        self.assertEqual(result.data["runs"][0]["opener"], "led")

    def test_missing_both_text_and_attachment_id_is_a_clean_error(self) -> None:
        result = nominate_repeated_opener_candidates(session=None)
        self.assertFalse(result.passed)
        self.assertEqual(result.findings[0]["severity"], "Critical")

    def test_unknown_attachment_id_is_a_clean_error_not_a_crash(self) -> None:
        session = Session(session_id="s", user_id="u")
        result = nominate_repeated_opener_candidates(attachment_id="does-not-exist", session=session)
        self.assertFalse(result.passed)
        self.assertEqual(result.findings[0]["severity"], "Critical")

    def test_attachment_without_cached_extraction_yet_is_a_clean_error(self) -> None:
        session = Session(session_id="s", user_id="u")
        attachment = session.add_attachment(filename="resume.docx", file_type="docx", data=b"")
        result = nominate_repeated_opener_candidates(attachment_id=attachment.id, session=session)
        self.assertFalse(result.passed)
        self.assertIn("No cached extracted text", result.findings[0]["issue"])


class TestNominateTenseInconsistencyCandidates(unittest.TestCase):
    """T-3.17. Zero prior coverage for this tool."""

    def test_present_tense_in_completed_role_is_flagged(self) -> None:
        result = nominate_tense_inconsistency_candidates(
            text="Led the migration. Team velocity is strong as a result.",
            is_current_role=False,
        )
        self.assertFalse(result.passed)
        self.assertEqual(len(result.data["candidates"]), 1)

    def test_past_tense_in_current_role_is_flagged(self) -> None:
        result = nominate_tense_inconsistency_candidates(
            text="Leads the migration. Managed the rollout last quarter.",
            is_current_role=True,
        )
        self.assertFalse(result.passed)
        self.assertEqual(len(result.data["candidates"]), 1)

    def test_consistent_past_tense_in_completed_role_passes(self) -> None:
        result = nominate_tense_inconsistency_candidates(
            text="Led the migration. Managed the rollout.",
            is_current_role=False,
        )
        self.assertTrue(result.passed)


if __name__ == "__main__":
    unittest.main()
