import tempfile
import unittest
from pathlib import Path

from app.spec_loader import ToolListEntry, parse_tool_list


class TestToolListEntryKinds(unittest.TestCase):
    def test_simple_kind_unchanged(self) -> None:
        entry = ToolListEntry(id="T-1.1", label="x", kind_text="TOOL")
        self.assertEqual(entry.kinds(), {"TOOL"})

    def test_compound_plus_separated_kinds(self) -> None:
        entry = ToolListEntry(id="T-1.1", label="x", kind_text="HYBRID + GATE")
        self.assertEqual(entry.kinds(), {"HYBRID", "GATE"})

    def test_descriptive_suffix_normalizes_to_leading_kind(self) -> None:
        """The real bug this pins: T-7.12's doc row reads 'TOOL trigger
        + JUDGMENT'. A tool registered as kind=TOOL must match against
        this, since 'trigger' describes how the TOOL is used, not a
        different enforcement kind."""
        entry = ToolListEntry(id="T-7.12", label="Portfolio-absence handling", kind_text="TOOL trigger + JUDGMENT")
        self.assertEqual(entry.kinds(), {"TOOL", "JUDGMENT"})
        self.assertIn("TOOL", entry.kinds())


class TestParseToolListGuard(unittest.TestCase):
    """Pins the batch 9 fix: a compound verdict phrase with no '+' at
    all (T-8.14's 'TOOL feeding JUDGMENT') was previously compared as
    one unbroken string against the known-kinds set, matched nothing,
    and the whole row was silently dropped from doc_entries even
    though it is a real verdict. That made a correctly-registered
    T-8.14 tool look, to test_spec_sync.py, like it had no matching
    row in the tool list at all."""

    def _parse(self, markdown: str):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tool-list.md"
            path.write_text(markdown, encoding="utf-8")
            return parse_tool_list(path)

    def test_compound_verdict_with_no_plus_delimiter_is_not_dropped(self) -> None:
        entries = self._parse(
            "| T-8.14 | AI-writing-detection pass | TOOL feeding JUDGMENT | Detectors produce signals. |\n"
        )
        self.assertIn("T-8.14", entries)
        # kinds() takes only the leading word of each '+'-separated
        # chunk; with no '+' at all that's "TOOL". The fix here is
        # that the row survives the guard, not a change to kinds().
        self.assertEqual(entries["T-8.14"].kinds(), {"TOOL"})

    def test_ordinary_plus_separated_verdict_still_parses(self) -> None:
        entries = self._parse("| T-0.4 | Colleague-name replacement | HYBRID + GATE | reasoning text |\n")
        self.assertIn("T-0.4", entries)
        self.assertEqual(entries["T-0.4"].kinds(), {"HYBRID", "GATE"})

    def test_non_verdict_row_is_still_skipped(self) -> None:
        """A row whose third column has no recognizable kind word at
        all (a genuinely unrelated table sharing the pipe-table shape)
        must still be dropped, not swept in by the looser split."""
        entries = self._parse("| T-9.99 | Something | Reasoning prose only | more text |\n")
        self.assertNotIn("T-9.99", entries)


if __name__ == "__main__":
    unittest.main()
