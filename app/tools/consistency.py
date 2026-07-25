"""
T-8.8: same-figure internal consistency.

Heuristic, not full NLP: extracts every (number, immediately-following
word) pair and groups by the following word, lowercased. If the same
referent word shows up paired with more than one distinct number, that
group is flagged. This catches the documented failure ("150 managers"
appearing three times with two different values) without needing real
coreference resolution. It will also produce false positives on
coincidental repeats (two different "5 years" claims about two
different things that happen to use the same following word) and false
negatives on referents phrased differently each time ("150 managers"
vs "150 leaders" vs "the same 150 people"). Flag it during Pedantic
review as a candidate list, not a verdict; a human or a JUDGMENT pass
still has to look at what it found.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Dict, List

from app.enforcement import EnforcementKind, ToolResult, tool

_NUMBER_WORD_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s+([a-zA-Z][a-zA-Z-]*)")


@tool(
    id="T-8.8",
    name="check_figure_consistency",
    description=(
        "Groups every (number, following word) pair in a document by "
        "the following word and flags any group where the same word is "
        "paired with more than one distinct number. Heuristic clustering, "
        "not coreference resolution; treat findings as candidates for "
        "the Pedantic pass to look at, not confirmed errors."
    ),
    kind=EnforcementKind.TOOL,
    input_schema={
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    },
)
def check_figure_consistency(text: str) -> ToolResult:
    groups: Dict[str, List[str]] = defaultdict(list)
    for number, word in _NUMBER_WORD_RE.findall(text):
        groups[word.lower()].append(number)

    findings = []
    for word, numbers in groups.items():
        distinct = sorted(set(numbers))
        if len(distinct) > 1:
            findings.append(
                {
                    "severity": "High",
                    "issue": f"'{word}' appears paired with inconsistent figures: {', '.join(distinct)}.",
                    "fix": "Confirm which value is correct against the Locked Facts Registry and make every instance agree.",
                }
            )
    return ToolResult(passed=len(findings) == 0, findings=findings)


@tool(
    id="T-8.9",
    name="check_figures_against_master",
    description=(
        "Cross-document check, distinct from check_figure_consistency "
        "(T-8.8), which clusters figures within one document. This "
        "extracts every number from the tailored text and flags any "
        "that does not appear anywhere in the master text at all, a "
        "figure with no traceable origin in the source of truth."
    ),
    kind=EnforcementKind.TOOL,
    input_schema={
        "type": "object",
        "properties": {
            "tailored_text": {"type": "string"},
            "master_text": {"type": "string"},
        },
        "required": ["tailored_text", "master_text"],
    },
)
def check_figures_against_master(tailored_text: str, master_text: str) -> ToolResult:
    tailored_numbers = {m.group(1) for m in re.finditer(r"\b(\d[\d,]*(?:\.\d+)?)\b", tailored_text)}
    master_numbers = {m.group(1) for m in re.finditer(r"\b(\d[\d,]*(?:\.\d+)?)\b", master_text)}

    untraceable = sorted(tailored_numbers - master_numbers)
    findings = [
        {
            "severity": "Critical",
            "issue": f"Figure '{number}' in the tailored text does not appear anywhere in the master.",
            "fix": "Confirm against the Locked Facts Registry; this figure has no traceable source.",
        }
        for number in untraceable
    ]
    return ToolResult(passed=len(untraceable) == 0, findings=findings, data={"untraceable_figures": untraceable})
