"""
T-8.8: same-figure internal consistency.

Heuristic, not full NLP: extracts every (number, immediately-following
word) pair and groups by the following word, lowercased. If the same
referent word shows up paired with more than one distinct number
*within the same role block*, that group is flagged.

Critical design decision (2026-07-26): the original implementation
ran this check on the whole document at once, which caused high false-
positive rates on legitimately different figures that happen to share
the same following word across different roles. "480 users" (PBT at
one point in time) and "56,583 users" (PBT at scale) are not
inconsistent — they are two distinct facts from two distinct contexts.
Conflating them across role boundaries is worse than not flagging at
all, because it trains the user to dismiss all flagged findings.

The fix: the tool now operates per-role-block. Inconsistency is only
flagged when the same word is paired with multiple values within one
role. Cross-role variation is expected and is never a finding.

When `roles` is not supplied (backward compat), the whole text is
treated as one block — same behavior as before, same false-positive
risk, but retained so callers don't break.

Each finding now includes the full sentence containing each flagged
number, not just the number and word, so the user has enough context
to verify without having to locate the bullet themselves (item 7 from
the 2026-07-26 review).
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Dict, List, Optional

from app.enforcement import EnforcementKind, ToolResult, tool

_NUMBER_WORD_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s+([a-zA-Z][a-zA-Z-]*)")
_SENTENCE_RE = re.compile(r"[^.!?\n]+[.!?\n]?")


def _sentences_containing(text: str, number: str, word: str) -> List[str]:
    """Returns up to 2 sentences from text that contain both the number
    and the word, for context surfacing in findings."""
    results = []
    for sentence in _SENTENCE_RE.findall(text):
        if number in sentence and word.lower() in sentence.lower():
            results.append(sentence.strip())
            if len(results) >= 2:
                break
    return results


def _check_block(block_text: str, block_label: str) -> List[Dict]:
    """Core consistency check for a single block of text."""
    groups: Dict[str, Dict[str, List[str]]] = defaultdict(lambda: defaultdict(list))

    for number, word in _NUMBER_WORD_RE.findall(block_text):
        # Store sentences for context, keyed by (word, number)
        sentences = _sentences_containing(block_text, number, word.lower())
        groups[word.lower()][number] = sentences or [f"...{number} {word}..."]

    findings = []
    for word, number_map in groups.items():
        distinct_numbers = sorted(number_map.keys())
        if len(distinct_numbers) <= 1:
            continue

        # Surface the actual sentences, not just the bare numbers
        context_lines = []
        for num in distinct_numbers:
            for sentence in number_map[num][:1]:
                context_lines.append(f"• {num} {word}: \"{sentence}\"")

        findings.append(
            {
                "severity": "High",
                "issue": (
                    f"'{word}' appears with inconsistent figures"
                    f"{' in ' + block_label if block_label else ''}: "
                    f"{', '.join(distinct_numbers)}.\n"
                    + "\n".join(context_lines)
                ),
                "fix": (
                    "Confirm which value is correct against the registry "
                    "and make every instance agree, or lock them as "
                    "separate facts with distinct role context if they "
                    "legitimately refer to different things."
                ),
            }
        )
    return findings


@tool(
    id="T-8.8",
    name="check_figure_consistency",
    description=(
        "Flags figures that appear with inconsistent values within the "
        "same role block. Takes either a flat `text` string (whole "
        "document, backward compat) or a `roles` list of "
        "{label, text} objects. Per-role checking eliminates the "
        "false positives that occur when the same word (e.g. 'users') "
        "legitimately has different values across different roles or "
        "time periods. Each finding includes the full sentence for "
        "context, not just the bare number."
    ),
    kind=EnforcementKind.TOOL,
    input_schema={
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "Whole-document text (single block, no role context).",
            },
            "roles": {
                "type": "array",
                "description": "Preferred: list of role blocks with labels.",
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string"},
                        "text": {"type": "string"},
                    },
                    "required": ["label", "text"],
                },
            },
        },
    },
)
def check_figure_consistency(
    text: Optional[str] = None,
    roles: Optional[List[Dict[str, str]]] = None,
) -> ToolResult:
    findings = []

    if roles:
        for role in roles:
            block_findings = _check_block(role.get("text", ""), role.get("label", ""))
            findings.extend(block_findings)
    elif text:
        findings = _check_block(text, "")
    else:
        return ToolResult(
            passed=False,
            findings=[{"severity": "Critical", "issue": "No text or roles provided.", "fix": "Pass either text or roles."}],
        )

    return ToolResult(passed=len(findings) == 0, findings=findings)


@tool(
    id="T-8.9",
    name="check_figures_against_foundational",
    description=(
        "Cross-document check, distinct from check_figure_consistency "
        "(T-8.8), which clusters figures within one document. This "
        "extracts every number from the tailored text and flags any "
        "that does not appear anywhere in the foundational-resume text "
        "at all, a figure with no traceable origin in the source of "
        "truth."
    ),
    kind=EnforcementKind.TOOL,
    input_schema={
        "type": "object",
        "properties": {
            "tailored_text": {"type": "string"},
            "foundational_text": {"type": "string"},
        },
        "required": ["tailored_text", "foundational_text"],
    },
)
def check_figures_against_foundational(tailored_text: str, foundational_text: str) -> ToolResult:
    tailored_numbers = {m.group(1) for m in re.finditer(r"\b(\d[\d,]*(?:\.\d+)?)\b", tailored_text)}
    foundational_numbers = {m.group(1) for m in re.finditer(r"\b(\d[\d,]*(?:\.\d+)?)\b", foundational_text)}

    untraceable = sorted(tailored_numbers - foundational_numbers)
    findings = [
        {
            "severity": "Critical",
            "issue": f"Figure '{number}' in the tailored text does not appear anywhere in the foundational resume.",
            "fix": "Confirm against the Locked Facts Registry; this figure has no traceable source.",
        }
        for number in untraceable
    ]
    return ToolResult(passed=len(untraceable) == 0, findings=findings, data={"untraceable_figures": untraceable})
