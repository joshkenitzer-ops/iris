"""
Loads the two spec documents from disk.

docs/iris-spec.md is loaded as text and sent as pinned, cached system
context on every Claude call (see app/claude_client.py). It is never
parsed or interpreted here; it is prose for the model to operate
under.

docs/iris-tool-list.md IS parsed, into a dict of id -> ToolListEntry.
Not because the harness runs on it, the harness runs on the ToolSpec
registry in app/enforcement.py, but because parsing it is what lets
tests/test_spec_sync.py compare the two: every id the code registers
against what the document says that id's enforcement kind is. That
comparison is the actual fix for the cross-file drift problem the spec
itself names (Decision Log, 2026-07-24) as a risk this file split
introduced. A parser that only skims the table is enough for that; it
does not need to understand the tool list's prose.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, NamedTuple

_ROW_RE = re.compile(
    r"^\|\s*(T-\d+\.\d+[a-z]?)\s*\|\s*(.+?)\s*\|\s*([A-Z][A-Za-z\s\+]*[A-Za-z])\s*\|"
)


class ToolListEntry(NamedTuple):
    id: str
    label: str
    kind_text: str  # raw text from the Verdict column, e.g. "TOOL + GATE"

    def kinds(self) -> set:
        """Split the Verdict column on '+' and normalize each part to
        its leading kind word. Some tool-list rows use a compound
        label like 'TOOL trigger' (T-7.12) to describe how a TOOL-kind
        item is used, not a different kind; comparing the full phrase
        against a plain 'TOOL' registration would report a false
        mismatch. Taking only the first word is intentional: it is
        the kind, everything after it is descriptive."""
        known = {"TOOL", "GATE", "HYBRID", "JUDGMENT", "HUMAN"}
        result = set()
        for part in self.kind_text.split("+"):
            first_word = part.strip().split()[0] if part.strip() else ""
            result.add(first_word if first_word in known else part.strip())
        return result


def load_spec_text(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError(f"Spec file at {path} is empty. Nothing to load.")
    return text


def parse_tool_list(path: Path) -> Dict[str, ToolListEntry]:
    entries: Dict[str, ToolListEntry] = {}
    known_kinds = {"TOOL", "GATE", "HYBRID", "JUDGMENT", "HUMAN"}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _ROW_RE.match(line.strip())
        if not match:
            continue
        tool_id, label, kind_text = match.groups()
        # Guard against matching a stray table row whose third column
        # isn't actually a verdict (e.g. a header separator or a
        # cross-reference table with different columns). Split on any
        # whitespace as well as '+': a compound verdict phrase with no
        # '+' delimiter at all (T-8.14: "TOOL feeding JUDGMENT") was
        # previously compared as one unbroken string against
        # known_kinds, matched nothing, and the whole row was silently
        # dropped even though it is a real verdict. ToolListEntry.kinds()
        # already splits on whitespace too; this guard now does the same.
        candidate_kinds = {w for w in re.split(r"[\s\+]+", kind_text) if w}
        if not candidate_kinds & known_kinds:
            continue
        entries[tool_id] = ToolListEntry(id=tool_id, label=label, kind_text=kind_text)
    return entries
