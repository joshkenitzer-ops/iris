"""
Regression coverage for the transcript-cost fix (2026-07-27).

An ingest result is not read once and discarded: it is appended to the
transcript and re-sent as input on every subsequent call for the life of
the session. Inlining a 338-page performance export therefore cost
~100,000 tokens PER TURN, roughly half the context window, for as long
as the session lived. These pin the split that fixes it without touching
the resume path that was already validated end to end.
"""

import unittest

from app.config import INLINE_EXTRACT_CHARS, MAX_TRANSCRIPT_CHARS, MAX_TRANSCRIPT_MESSAGES
from app.session import Session
from app.tools.intake import read_attachment_text


class TestExtractionPayloadSizeSplit(unittest.TestCase):
    def setUp(self) -> None:
        self.session = Session(session_id="s", user_id="u")

    def _payload(self, char_count: int) -> dict:
        from app.tools.intake import _extraction_payload

        attachment = self.session.add_attachment("doc.pdf", "pdf", b"x")
        text = "y" * char_count
        attachment.extracted_text = text
        return _extraction_payload(text, "uploaded .pdf", attachment, {"page_count": 1})

    def test_resume_sized_document_is_still_inlined_whole(self) -> None:
        """The validated path must not change: a resume (largest tested
        ~31,000 chars) keeps arriving complete, in one piece."""
        payload = self._payload(31_000)
        self.assertTrue(payload["is_complete"])
        self.assertNotIn("next_step", payload)
        self.assertEqual(payload["raw_char_count"], 31_000)
        self.assertIn("y" * 100, payload["extracted_text"])

    def test_document_at_the_boundary_is_still_inlined(self) -> None:
        payload = self._payload(INLINE_EXTRACT_CHARS)
        self.assertTrue(payload["is_complete"])

    def test_oversized_document_returns_a_preview_and_paging_instructions(self) -> None:
        payload = self._payload(INLINE_EXTRACT_CHARS + 50_000)
        self.assertFalse(payload["is_complete"])
        self.assertEqual(payload["preview_char_count"], INLINE_EXTRACT_CHARS)
        self.assertIn("read_attachment_text", payload["next_step"])
        # The whole point: the inlined portion is bounded regardless of
        # how large the source document is.
        self.assertLess(len(payload["extracted_text"]), INLINE_EXTRACT_CHARS + 2_000)

    def test_oversized_payload_still_reports_the_true_total(self) -> None:
        """A preview must not misreport the document's real size, or the
        model will reason about it as if it were small."""
        payload = self._payload(400_000)
        self.assertEqual(payload["raw_char_count"], 400_000)
        self.assertIn("400000", payload["next_step"])


class TestReadAttachmentText(unittest.TestCase):
    def setUp(self) -> None:
        self.session = Session(session_id="s", user_id="u")
        self.attachment = self.session.add_attachment("perf.pdf", "pdf", b"x")
        self.attachment.extracted_text = "".join(str(i % 10) for i in range(100_000))

    def test_reads_from_an_offset_and_reports_where_to_continue(self) -> None:
        result = read_attachment_text(self.attachment.id, session=self.session, offset=0, length=1_000)
        self.assertTrue(result.passed)
        self.assertEqual(result.data["offset"], 0)
        self.assertEqual(result.data["next_offset"], 1_000)
        self.assertTrue(result.data["has_more"])
        self.assertEqual(result.data["total_char_count"], 100_000)

    def test_paging_through_reaches_the_end_and_stops(self) -> None:
        offset, reads = 0, 0
        while True:
            result = read_attachment_text(self.attachment.id, session=self.session, offset=offset, length=40_000)
            reads += 1
            if not result.data["has_more"]:
                break
            offset = result.data["next_offset"]
            self.assertLess(reads, 10, "paging failed to terminate")
        self.assertEqual(result.data["next_offset"], 100_000)

    def test_span_is_capped_regardless_of_requested_length(self) -> None:
        """Otherwise the tool becomes a way to re-inline the whole
        document in one call, defeating its own purpose."""
        result = read_attachment_text(self.attachment.id, session=self.session, offset=0, length=10_000_000)
        self.assertLessEqual(len(result.data["text"]), 45_000)

    def test_offset_past_the_end_is_a_clean_empty_read_not_an_error(self) -> None:
        result = read_attachment_text(self.attachment.id, session=self.session, offset=500_000)
        self.assertTrue(result.passed)
        self.assertFalse(result.data["has_more"])

    def test_unknown_attachment_is_a_finding_not_a_crash(self) -> None:
        result = read_attachment_text("nope", session=self.session)
        self.assertFalse(result.passed)
        self.assertEqual(result.findings[0]["severity"], "Critical")

    def test_unextracted_attachment_says_to_ingest_first(self) -> None:
        fresh = self.session.add_attachment("other.pdf", "pdf", b"x")
        result = read_attachment_text(fresh.id, session=self.session)
        self.assertFalse(result.passed)
        self.assertIn("ingest_document", result.findings[0]["fix"])

    def test_returned_span_is_wrapped_as_untrusted(self) -> None:
        """Document text stays inside the untrusted-content boundary no
        matter which tool hands it over."""
        result = read_attachment_text(self.attachment.id, session=self.session, offset=0, length=100)
        self.assertIn("UNTRUSTED", result.data["text"])


class TestTranscriptCharacterBackstop(unittest.TestCase):
    def test_oversized_transcript_is_trimmed_by_characters(self) -> None:
        session = Session(session_id="s", user_id="u")
        big = "x" * 50_000
        session.append_messages([{"role": "user", "content": big} for _ in range(20)])
        self.assertLessEqual(session.transcript_chars(), MAX_TRANSCRIPT_CHARS)

    def test_count_cap_still_applies_to_small_messages(self) -> None:
        session = Session(session_id="s", user_id="u")
        session.append_messages([{"role": "user", "content": "hi"} for _ in range(MAX_TRANSCRIPT_MESSAGES + 40)])
        self.assertLessEqual(len(session.messages), MAX_TRANSCRIPT_MESSAGES)

    def test_newest_message_survives_even_if_it_alone_exceeds_the_budget(self) -> None:
        """Dropping the turn the model is mid-way through is worse than
        briefly exceeding a soft ceiling."""
        session = Session(session_id="s", user_id="u")
        session.append_messages([{"role": "user", "content": "x" * (MAX_TRANSCRIPT_CHARS + 10_000)}])
        self.assertEqual(len(session.messages), 1)

    def test_trimming_keeps_the_most_recent_messages(self) -> None:
        session = Session(session_id="s", user_id="u")
        session.append_messages([{"role": "user", "content": "x" * 60_000} for _ in range(10)])
        session.append_messages([{"role": "user", "content": "NEWEST"}])
        self.assertEqual(session.messages[-1]["content"], "NEWEST")


if __name__ == "__main__":
    unittest.main()
