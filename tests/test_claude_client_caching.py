import unittest

from app.claude_client import _with_cache_breakpoint


class TestWithCacheBreakpoint(unittest.TestCase):
    """Regression coverage for the missing-message-caching latency fix:
    only the system block (spec_text) carried cache_control, so every
    tool-loop iteration re-sent the whole accumulated transcript as
    fresh, uncached input tokens. `_with_cache_breakpoint` must mark the
    last block of the last message for caching without ever mutating
    the caller's list, since that list is also what gets persisted to
    session storage between turns."""

    def test_empty_messages_returned_unchanged(self) -> None:
        self.assertEqual(_with_cache_breakpoint([]), [])

    def test_string_content_wrapped_with_marker(self) -> None:
        messages = [{"role": "user", "content": "hello"}]
        result = _with_cache_breakpoint(messages)
        self.assertEqual(
            result,
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "hello", "cache_control": {"type": "ephemeral"}}
                    ],
                }
            ],
        )
        # Original untouched — still a plain string.
        self.assertEqual(messages[0]["content"], "hello")

    def test_list_content_marks_last_block_only(self) -> None:
        messages = [
            {"role": "user", "content": "earlier turn"},
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "t1", "content": "{}"},
                    {"type": "tool_result", "tool_use_id": "t2", "content": "{}"},
                ],
            },
        ]
        result = _with_cache_breakpoint(messages)
        last_content = result[-1]["content"]
        self.assertNotIn("cache_control", last_content[0])
        self.assertEqual(last_content[1]["cache_control"], {"type": "ephemeral"})
        # Earlier messages are passed through unchanged (same object is fine).
        self.assertEqual(result[0], messages[0])

    def test_does_not_mutate_input_list_or_blocks(self) -> None:
        original_block = {"type": "tool_result", "tool_use_id": "t1", "content": "{}"}
        messages = [{"role": "user", "content": [original_block]}]
        _with_cache_breakpoint(messages)
        self.assertNotIn("cache_control", original_block)
        self.assertNotIn("cache_control", messages[0]["content"][0])

    def test_repeated_calls_across_growing_transcript_each_add_one_fresh_marker(self) -> None:
        # Simulates successive tool-loop iterations: each call sees a
        # longer working_messages, and only ever adds a marker to
        # whatever is now the last block - never accumulating markers
        # on earlier messages the way an in-place mutation would.
        working_messages = [{"role": "user", "content": "start"}]
        for i in range(3):
            working_messages = working_messages + [
                {"role": "assistant", "content": [{"type": "text", "text": f"turn {i}"}]}
            ]
            result = _with_cache_breakpoint(working_messages)
            markers = [
                block
                for m in result
                if isinstance(m.get("content"), list)
                for block in m["content"]
                if "cache_control" in block
            ]
            self.assertEqual(len(markers), 1)
            # working_messages itself (what gets persisted) stays clean.
            self.assertTrue(
                all(
                    "cache_control" not in block
                    for m in working_messages
                    if isinstance(m.get("content"), list)
                    for block in m["content"]
                )
            )


if __name__ == "__main__":
    unittest.main()
