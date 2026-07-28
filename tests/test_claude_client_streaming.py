import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import app.claude_client as claude_client_module
from app.claude_client import stream_turn
from app.session import Session


class _FakeMessageStream:
    """Stands in for the SDK's `client.messages.stream(...)` context
    manager: a fixed list of text chunks plus the final accumulated
    Message (content blocks + stop_reason)."""

    def __init__(self, text_chunks, content_blocks, stop_reason):
        self._text_chunks = text_chunks
        self._final = SimpleNamespace(content=content_blocks, stop_reason=stop_reason)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    @property
    def text_stream(self):
        return iter(self._text_chunks)

    def get_final_message(self):
        return self._final


def _fake_client_with_turns(turns):
    """Each call to client.messages.stream(...) pops the next scripted
    turn, same shape stream_turn's own tool loop expects: one call per
    loop iteration."""
    calls = {"n": 0}

    def _stream(**kwargs):
        turn = turns[calls["n"]]
        calls["n"] += 1
        return _FakeMessageStream(turn["text_chunks"], turn["content_blocks"], turn["stop_reason"])

    fake = MagicMock()
    fake.messages.stream.side_effect = _stream
    return fake


class TestStreamTurnTextReset(unittest.TestCase):
    """Regression coverage for the 2026-07-27 narration-clutter fix: a
    tool_use turn's streamed text is preamble the model produced with no
    private scratchpad to put it in instead (Sonnet 4.6 at EFFORT=medium
    runs no thinking budget, config.py), and it must not survive into
    what the user sees. Only the turn that actually ends the
    conversation (stop_reason != "tool_use") keeps its text."""

    def setUp(self) -> None:
        self.session = Session(session_id="s", user_id="u")

    def _run(self, turns):
        with patch.object(claude_client_module, "_client", return_value=_fake_client_with_turns(turns)):
            return list(
                stream_turn(
                    spec_text="spec",
                    messages=[{"role": "user", "content": "hi"}],
                    session=self.session,
                    tool_ids=["T-3.1"],
                )
            )

    def test_text_reset_fires_after_a_tool_use_turn_with_preamble(self) -> None:
        turns = [
            {
                "text_chunks": ["Let me check this."],
                "content_blocks": [
                    SimpleNamespace(type="text", text="Let me check this."),
                    SimpleNamespace(type="tool_use", id="t1", name="check_em_dash", input={"text": "no dash here"}),
                ],
                "stop_reason": "tool_use",
            },
            {
                "text_chunks": ["All checks passed."],
                "content_blocks": [SimpleNamespace(type="text", text="All checks passed.")],
                "stop_reason": "end_turn",
            },
        ]
        events = self._run(turns)
        types_seen = [e["type"] for e in events]

        self.assertIn("text_reset", types_seen)
        reset_index = types_seen.index("text_reset")
        # Fires right after the preamble delta, before the batched tool dispatch.
        self.assertEqual(types_seen[reset_index - 1], "text_delta")
        self.assertIn("tool_call", types_seen[reset_index:])

        done_event = events[-1]
        self.assertEqual(done_event["type"], "done")
        self.assertEqual(done_event["text"], "All checks passed.")

    def test_no_text_reset_when_the_first_turn_is_already_final(self) -> None:
        turns = [
            {
                "text_chunks": ["Straight to the answer."],
                "content_blocks": [SimpleNamespace(type="text", text="Straight to the answer.")],
                "stop_reason": "end_turn",
            },
        ]
        events = self._run(turns)
        types_seen = [e["type"] for e in events]
        self.assertNotIn("text_reset", types_seen)
        self.assertEqual(events[-1]["text"], "Straight to the answer.")

    def test_no_text_reset_when_a_tool_use_turn_streamed_no_text(self) -> None:
        turns = [
            {
                "text_chunks": [],
                "content_blocks": [
                    SimpleNamespace(type="tool_use", id="t1", name="check_em_dash", input={"text": "clean"}),
                ],
                "stop_reason": "tool_use",
            },
            {
                "text_chunks": ["Done."],
                "content_blocks": [SimpleNamespace(type="text", text="Done.")],
                "stop_reason": "end_turn",
            },
        ]
        events = self._run(turns)
        types_seen = [e["type"] for e in events]
        # No preamble text streamed on the tool_use turn, so nothing to discard.
        self.assertNotIn("text_reset", types_seen)


if __name__ == "__main__":
    unittest.main()


class TestRunTurnWrapsStreamTurn(unittest.TestCase):
    """run_turn had no CI coverage at all: its only test is the paid
    smoke test, which skips without ANTHROPIC_API_KEY. That is precisely
    how it drifted five fixes behind stream_turn before being
    consolidated (2026-07-27). Same fake client, so this runs offline."""

    def setUp(self) -> None:
        self.session = Session(session_id="s", user_id="u")

    def _run(self, turns, **kwargs):
        from app.claude_client import run_turn

        with patch.object(claude_client_module, "_client", return_value=_fake_client_with_turns(turns)):
            return run_turn(
                spec_text="spec",
                messages=[{"role": "user", "content": "hi"}],
                session=self.session,
                **kwargs,
            )

    def test_returns_the_final_text_and_transcript(self) -> None:
        result = self._run([{
            "text_chunks": ["All done."],
            "content_blocks": [SimpleNamespace(type="text", text="All done.")],
            "stop_reason": "end_turn",
        }])
        self.assertEqual(result["text"], "All done.")
        self.assertEqual(result["messages"][-1]["role"], "assistant")

    def test_drives_the_tool_loop_to_completion(self) -> None:
        turns = [
            {
                "text_chunks": [],
                "content_blocks": [
                    SimpleNamespace(type="tool_use", id="t1", name="check_em_dash", input={"text": "clean"}),
                ],
                "stop_reason": "tool_use",
            },
            {
                "text_chunks": ["Checked."],
                "content_blocks": [SimpleNamespace(type="text", text="Checked.")],
                "stop_reason": "end_turn",
            },
        ]
        self.assertEqual(self._run(turns)["text"], "Checked.")

    def test_inherits_the_em_dash_sanitizer(self) -> None:
        """A fix that had to be applied to both copies by hand. Now it
        cannot be applied to only one."""
        result = self._run([{
            "text_chunks": ["Two findings — both minor."],
            "content_blocks": [SimpleNamespace(type="text", text="Two findings — both minor.")],
            "stop_reason": "end_turn",
        }])
        self.assertNotIn("—", result["text"])

    def test_exhausted_tool_loop_raises_rather_than_returning_empty(self) -> None:
        from app.claude_client import ToolLoopExhausted

        looping = [{
            "text_chunks": [],
            "content_blocks": [SimpleNamespace(type="tool_use", id="t", name="check_em_dash", input={"text": "x"})],
            "stop_reason": "tool_use",
        }] * 6
        with self.assertRaises(ToolLoopExhausted):
            self._run(looping, max_tool_iterations=3)

    def test_upstream_failure_raises_upstream_model_error(self) -> None:
        import anthropic

        from app.claude_client import UpstreamModelError, run_turn

        fake = MagicMock()
        fake.messages.stream.side_effect = anthropic.APIError("boom", request=MagicMock(), body=None)
        with patch.object(claude_client_module, "_client", return_value=fake):
            with self.assertRaises(UpstreamModelError):
                run_turn(spec_text="spec", messages=[{"role": "user", "content": "hi"}], session=self.session)
