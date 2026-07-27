import unittest
from types import SimpleNamespace

from app.claude_client import _blocks_to_plain, _sanitize_assistant_text


class TestSanitizeAssistantText(unittest.TestCase):
    """Regression coverage for the mechanical em-dash backstop: Principle
    10 already told the model never to use an em dash in its own
    conversational output, and it was observed violating that rule live
    anyway. This makes the rule hold regardless of what the model does."""

    def test_text_without_em_dash_is_unchanged(self) -> None:
        self.assertEqual(_sanitize_assistant_text("Two Criticals need your review."), "Two Criticals need your review.")

    def test_em_dash_between_words_becomes_a_comma(self) -> None:
        self.assertEqual(
            _sanitize_assistant_text("Two Criticals — both in Experience."),
            "Two Criticals, both in Experience.",
        )

    def test_multiple_em_dashes_all_replaced(self) -> None:
        result = _sanitize_assistant_text("One — two — three.")
        self.assertNotIn("—", result)
        self.assertEqual(result, "One, two, three.")

    def test_bare_em_dash_with_no_surrounding_space_is_still_replaced(self) -> None:
        result = _sanitize_assistant_text("word—word")
        self.assertNotIn("—", result)

    def test_empty_string_returns_empty_string(self) -> None:
        self.assertEqual(_sanitize_assistant_text(""), "")


class TestBlocksToPlainSanitizesTextOnly(unittest.TestCase):
    """The sanitizer applies to Iris's own conversational text blocks.
    Tool-use input (resume/cover-letter content, structured tool
    arguments) is left untouched here — that content is governed by
    check_em_dash (T-3.1) running against the actual rendered document,
    not by this harness-level backstop, and blindly rewriting tool
    arguments risks corrupting structured data a tool expects verbatim."""

    def test_text_block_em_dash_is_stripped(self) -> None:
        blocks = [SimpleNamespace(type="text", text="Findings — two Criticals.")]
        plain = _blocks_to_plain(blocks)
        self.assertEqual(plain, [{"type": "text", "text": "Findings, two Criticals."}])

    def test_tool_use_input_is_not_touched(self) -> None:
        blocks = [
            SimpleNamespace(
                type="tool_use",
                id="t1",
                name="render_resume_docx",
                input={"sections": [{"heading": "Experience", "body": "Led work — shipped it."}]},
            )
        ]
        plain = _blocks_to_plain(blocks)
        self.assertEqual(
            plain,
            [
                {
                    "type": "tool_use",
                    "id": "t1",
                    "name": "render_resume_docx",
                    "input": {"sections": [{"heading": "Experience", "body": "Led work — shipped it."}]},
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
