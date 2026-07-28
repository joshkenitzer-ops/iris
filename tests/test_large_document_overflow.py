"""
Regression coverage for the 2026-07-28 context-overflow incident.

A new-user test uploaded a 338-page performance export. Ingestion
worked, the model summarized it, the user answered a follow-up, and the
next request came back as an HTTP 400 that the UI reported as "this
conversation may have grown too long."

Two distinct bugs, both introduced by the 2026-07-27 fixes:

  1. run_batch_checks resolved the full cached text server-side and
     returned a finding for every hit. Measured on a document that size:
     5,002 findings, 850,613 characters, ~212,000 tokens in ONE tool
     result, exceeding Sonnet's entire 200,000-token window before the
     spec or tool schemas were added. INLINE_EXTRACT_CHARS had bounded
     what ingest INLINES; nothing bounded what the checks RETURN.

  2. trim_transcript then popped messages by character budget with no
     awareness of tool_use/tool_result pairing, orphaning a tool_result
     at the head of the stored transcript. The API rejects that shape,
     and because it persisted, every later turn rebuilt the same invalid
     request. The session was unrecoverable, which is why "start a new
     session" was the only way out.
"""

import json
import unittest

import app.tools  # noqa: F401  (registers tools)
from app.config import (
    MAX_FINDINGS_PER_BATCH,
    MAX_FINDINGS_PER_CHECK,
    MAX_TRANSCRIPT_CHARS,
)
from app.enforcement import registry
from app.session import Session

# Dense in flagged patterns, the way a real multi-year performance
# export is: repeated hedges, banned vocabulary, parallel triples.
_NOISY_PARAGRAPH = (
    "Led the initiative and delivered results. Effectively managed stakeholders. "
    "Directly shaped the roadmap. Scoped, documented, and built the system. "
)
_PHASE1_TEXT_CHECKS = ["T-3.1", "T-3.3", "T-3.10", "T-3.11", "T-3.12", "T-3.13"]


def _session_with_cached_text(char_target: int):
    session = Session(session_id="s", user_id="u")
    attachment = session.add_attachment("perf.pdf", "pdf", b"x")
    repeats = (char_target // len(_NOISY_PARAGRAPH)) + 1
    attachment.extracted_text = (_NOISY_PARAGRAPH * repeats)[:char_target]
    return session, attachment.id


def _model_visible_size(result) -> int:
    """What actually crosses the wire. claude_client strips `data` from
    batch results, so only passed + findings reach the model; measuring
    the full ToolResult would overstate what costs context."""
    return len(json.dumps({"passed": result.passed, "findings": result.findings}, default=str))


class TestBatchFindingsAreBounded(unittest.TestCase):
    def setUp(self) -> None:
        self.session, self.attachment_id = _session_with_cached_text(700_000)

    def _run(self, tool_ids=None):
        return registry.dispatch(
            "run_batch_checks",
            {"tool_ids": tool_ids or _PHASE1_TEXT_CHECKS, "inputs": {"attachment_id": self.attachment_id}},
            session=self.session,
        )

    def test_a_huge_document_no_longer_overflows_the_context_window(self) -> None:
        """The headline regression. Before the cap this single result was
        ~212,000 tokens against a 200,000-token window."""
        approx_tokens = _model_visible_size(self._run()) // 4
        self.assertLess(approx_tokens, 20_000)

    def test_findings_are_capped_per_check(self) -> None:
        """Per-check, not only overall, so one noisy sweep cannot crowd
        every other check out of the result."""
        result = self._run()
        for entry in result.data["summary"]:
            self.assertLessEqual(entry["returned_count"], MAX_FINDINGS_PER_CHECK)

    def test_total_findings_respect_the_batch_ceiling(self) -> None:
        result = self._run()
        # Truncation notices are appended on top of the capped set, one
        # per truncated check plus at most one batch-level notice.
        self.assertLessEqual(len(result.findings), MAX_FINDINGS_PER_BATCH + len(_PHASE1_TEXT_CHECKS) + 1)

    def test_truncation_is_disclosed_in_findings_not_only_in_data(self) -> None:
        """claude_client strips `data` from batch results, so a count
        recorded only there is invisible to the model. Returning 20 of
        5,002 silently would let it conclude the document is clean."""
        result = self._run()
        notices = [f for f in result.findings if "not listed" in f.get("issue", "")]
        self.assertTrue(notices)
        self.assertTrue(any(str(entry["finding_count"]) in n["issue"] for entry in result.data["summary"] for n in notices))

    def test_true_totals_are_still_reported(self) -> None:
        result = self._run()
        self.assertGreater(result.data["suppressed_finding_count"], 0)
        self.assertTrue(any(e["finding_count"] > e["returned_count"] for e in result.data["summary"]))

    def test_severity_survives_truncation(self) -> None:
        """A Critical must never be dropped in favour of a Low. An
        unordered truncation over a long document would keep whichever
        findings happened to sort last."""
        from app.tools.intake import _cap_findings

        findings = [{"severity": "Low", "issue": f"low {i}"} for i in range(50)]
        findings.append({"severity": "Critical", "issue": "the one that blocks delivery"})
        kept, suppressed = _cap_findings(findings, 5)
        self.assertEqual(suppressed, 46)
        self.assertEqual(kept[0]["severity"], "Critical")

    def test_a_small_document_is_untouched(self) -> None:
        """The cap must not change behaviour for an ordinary resume."""
        session, attachment_id = _session_with_cached_text(2_000)
        result = registry.dispatch(
            "run_batch_checks",
            {"tool_ids": ["T-3.3"], "inputs": {"attachment_id": attachment_id}},
            session=session,
        )
        self.assertEqual(result.data["suppressed_finding_count"], 0)
        self.assertFalse([f for f in result.findings if "not listed" in f.get("issue", "")])


class TestTrimNeverOrphansAToolResult(unittest.TestCase):
    @staticmethod
    def _head_block_type(session: Session):
        if not session.messages:
            return None
        content = session.messages[0].get("content")
        return content[0].get("type") if isinstance(content, list) else "text"

    def test_orphaned_tool_result_is_dropped_not_left_at_the_head(self) -> None:
        """The exact shape that produced the permanent 400."""
        session = Session(session_id="s", user_id="u")
        session.messages = [
            {"role": "user", "content": "x" * 100_000},
            {"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": "run_batch_checks", "input": {}}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "y" * (MAX_TRANSCRIPT_CHARS + 10_000)}]},
        ]
        session.trim_transcript()
        self.assertNotEqual(self._head_block_type(session), "tool_result")

    def test_emptying_the_transcript_is_preferred_to_keeping_an_invalid_one(self) -> None:
        """A tool_result at the head is orphaned by definition, so
        dropping it is right however few messages remain. Keeping one
        invalid message would preserve the 400 forever."""
        session = Session(session_id="s", user_id="u")
        session.messages = [
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "orphan"}]},
        ]
        session.trim_transcript()
        self.assertEqual(session.messages, [])

    def test_session_recovers_on_the_next_turn(self) -> None:
        """The property that actually matters: after trimming to empty,
        the next user message starts a valid conversation rather than
        rebuilding the rejected request."""
        session = Session(session_id="s", user_id="u")
        session.messages = [
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "orphan"}]},
        ]
        session.trim_transcript()
        session.append_messages([{"role": "user", "content": "carry on"}])
        self.assertEqual(len(session.messages), 1)
        self.assertEqual(session.messages[0]["content"], "carry on")
        self.assertNotEqual(self._head_block_type(session), "tool_result")

    def test_a_healthy_transcript_is_left_alone(self) -> None:
        session = Session(session_id="s", user_id="u")
        session.messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": "check_em_dash", "input": {}}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "ok"}]},
        ]
        session.trim_transcript()
        self.assertEqual(len(session.messages), 3)

    def test_plain_string_content_is_handled(self) -> None:
        """Ordinary user turns carry a string, tool turns carry a list.
        The pairing check has to handle both without raising."""
        session = Session(session_id="s", user_id="u")
        session.messages = [{"role": "user", "content": "just text"}]
        session.trim_transcript()
        self.assertEqual(len(session.messages), 1)


if __name__ == "__main__":
    unittest.main()
