"""
This is the actual fix for the cross-file drift the spec's own Decision
Log names as a risk (2026-07-24: "splitting rules from enforcement
created a new failure surface... nothing in the spec guards this").

It does not guard every possible drift, prose can still diverge from
code in ways no parser catches, but it guarantees one concrete thing:
a tool registered in app/enforcement.py cannot silently disagree with
docs/iris-tool-list.md about its own enforcement kind. If someone
edits the tool list to change T-3.1 from GATE to TOOL without updating
the decorator in app/tools/slop.py, or the reverse, this fails on the
next run, in CI, before it ships as a quiet inconsistency.

Run this in CI on every PR that touches app/tools/**, app/enforcement.py,
or docs/iris-tool-list.md.
"""

import unittest
from pathlib import Path

import app.tools  # noqa: F401  (registers everything via decorator side effects)
from app.enforcement import registry
from app.spec_loader import parse_tool_list

DOCS_PATH = Path(__file__).resolve().parent.parent / "docs" / "iris-tool-list.md"


class TestSpecSync(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.doc_entries = parse_tool_list(DOCS_PATH)

    def test_docs_file_parses_to_a_reasonable_number_of_entries(self) -> None:
        # Sanity floor. If this drops near zero, the parser broke
        # against a reformatted table, not that the tool list shrank.
        self.assertGreater(len(self.doc_entries), 90)

    def test_every_registered_tool_exists_in_the_tool_list(self) -> None:
        missing = [spec.id for spec in registry.all() if spec.id not in self.doc_entries]
        self.assertEqual(
            missing,
            [],
            f"Tool(s) registered in code with no matching row in "
            f"docs/iris-tool-list.md: {missing}. Either the id is wrong "
            f"in code, or the doc row was edited/removed without "
            f"updating the implementation.",
        )

    def test_registered_kind_matches_documented_kind(self) -> None:
        mismatches = []
        for spec in registry.all():
            doc_entry = self.doc_entries.get(spec.id)
            if doc_entry is None:
                continue  # already reported by the previous test
            if spec.kind.value not in doc_entry.kinds():
                mismatches.append(
                    f"{spec.id}: code says {spec.kind.value}, "
                    f"docs say {doc_entry.kind_text}"
                )
        self.assertEqual(
            mismatches,
            [],
            "Enforcement kind mismatch between code and the tool list: "
            + "; ".join(mismatches),
        )

    def test_blocking_flag_agrees_with_gate_kind(self) -> None:
        """Every GATE-kind tool should be marked blocking=True in code
        (spec rule 4.1/4.4: a gate is checked server-side, not left to
        the model's discretion). A GATE that isn't marked blocking is a
        tool that looks enforced in the spec but isn't in the harness."""
        for spec in registry.all():
            if spec.kind.value == "GATE":
                self.assertTrue(
                    spec.blocking,
                    f"{spec.id} is kind=GATE but blocking=False. A GATE "
                    f"that doesn't block isn't a gate.",
                )


if __name__ == "__main__":
    unittest.main()
