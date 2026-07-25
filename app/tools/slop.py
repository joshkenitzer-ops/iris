"""Phase 3 slop checks. See docs/iris-spec.md section 6, Phase 3."""

from __future__ import annotations

import re
from typing import List

from app.config import BANNED_TERM_FREQUENCY_THRESHOLD
from app.enforcement import EnforcementKind, ToolResult, tool

EM_DASH = "\u2014"

ALWAYS_FLAGGED_TERMS = [
    "seamlessly",
    "leveraged",
    "utilized",
    "spearheaded",
    "synergized",
    "through-line",
    "established clear expectations",
    "intellectual foundation",
    "what I bring to this role",
]

FREQUENCY_GATED_TERMS = ["effectively", "directly"]


@tool(
    id="T-3.1",
    name="check_em_dash",
    description=(
        "Scans text for em dashes. Iris never uses an em dash in any "
        "generated output, no exceptions. Call this on every draft "
        "before it is considered final."
    ),
    kind=EnforcementKind.GATE,
    input_schema={
        "type": "object",
        "properties": {"text": {"type": "string", "description": "Text to scan."}},
        "required": ["text"],
    },
    blocking=True,
)
def check_em_dash(text: str) -> ToolResult:
    count = text.count(EM_DASH)
    if count == 0:
        return ToolResult(passed=True)
    return ToolResult(
        passed=False,
        findings=[
            {
                "severity": "Critical",
                "issue": f"{count} em dash(es) found.",
                "fix": "Replace each with a period, comma, or colon.",
            }
        ],
    )


@tool(
    id="T-3.3",
    name="check_banned_vocabulary",
    description=(
        "Checks text against the default banned-vocabulary list. Two "
        "tiers: always-flagged terms fire on any occurrence; "
        "frequency-gated terms ('effectively', 'directly') are ordinary "
        "English and only flag above a per-document threshold. Does not "
        "assess misuse below the threshold, that is check_banned_vocabulary_misuse."
    ),
    kind=EnforcementKind.TOOL,
    input_schema={
        "type": "object",
        "properties": {"text": {"type": "string", "description": "Text to scan."}},
        "required": ["text"],
    },
)
def check_banned_vocabulary(text: str) -> ToolResult:
    lowered = text.lower()
    findings = []

    for term in ALWAYS_FLAGGED_TERMS:
        occurrences = lowered.count(term)
        if occurrences:
            findings.append(
                {
                    "severity": "Medium",
                    "issue": f'"{term}" used {occurrences} time(s).',
                    "fix": "Replace with plain, direct language specific to the claim.",
                }
            )

    frequency_counts = {}
    for term in FREQUENCY_GATED_TERMS:
        occurrences = lowered.count(term)
        if occurrences:
            frequency_counts[term] = occurrences
        if occurrences > BANNED_TERM_FREQUENCY_THRESHOLD:
            findings.append(
                {
                    "severity": "Low",
                    "issue": (
                        f'"{term}" used {occurrences} times, above the '
                        f"threshold of {BANNED_TERM_FREQUENCY_THRESHOLD}."
                    ),
                    "fix": "Vary the language or cut the qualifier where it adds nothing.",
                }
            )

    return ToolResult(
        passed=len(findings) == 0,
        findings=findings,
        data={"frequency_gated_counts": frequency_counts},
    )


@tool(
    id="T-3.4",
    name="check_user_defined_terms",
    description=(
        "Checks text against a user-supplied banned-term list: personal "
        "or employer-specific terms, internal codenames, retired jargon. "
        "Same matching engine as check_banned_vocabulary but the list is "
        "user data, not spec content, per the product-scope decision "
        "that rules specific to one user's record are not spec rules."
    ),
    kind=EnforcementKind.TOOL,
    input_schema={
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "terms": {
                "type": "array",
                "items": {"type": "string"},
                "description": "The user's own banned-term list.",
            },
        },
        "required": ["text", "terms"],
    },
)
def check_user_defined_terms(text: str, terms: List[str]) -> ToolResult:
    lowered = text.lower()
    findings = []
    for term in terms:
        term_lower = term.strip().lower()
        if not term_lower:
            continue
        occurrences = lowered.count(term_lower)
        if occurrences:
            findings.append(
                {
                    "severity": "Medium",
                    "issue": f'User-banned term "{term}" used {occurrences} time(s).',
                    "fix": "Remove or replace with a plain descriptor.",
                }
            )
    return ToolResult(passed=len(findings) == 0, findings=findings)


_VAGUE_QUANTIFIERS = [
    "significantly",
    "substantially",
    "greatly",
    "dramatically",
    "considerably",
    "notably",
    "markedly",
    "vastly",
]
_DIGIT_RE = re.compile(r"\d")


@tool(
    id="T-3.5",
    name="check_vague_metrics",
    description=(
        "Flags quantifier claims with no attached number, e.g. "
        "'significantly improved throughput' with no figure anywhere "
        "nearby. A quantifier word is fine when a real number sits "
        "within a short window of it; flagged only when none does."
    ),
    kind=EnforcementKind.TOOL,
    input_schema={
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "window_words": {
                "type": "integer",
                "description": "How many words on either side count as 'nearby'. Default 8.",
            },
        },
        "required": ["text"],
    },
)
def check_vague_metrics(text: str, window_words: int = 8) -> ToolResult:
    words = text.split()
    lowered_words = [w.strip(".,;:()").lower() for w in words]
    findings = []
    for i, word in enumerate(lowered_words):
        if word not in _VAGUE_QUANTIFIERS:
            continue
        start = max(0, i - window_words)
        end = min(len(words), i + window_words + 1)
        nearby = " ".join(words[start:end])
        if not _DIGIT_RE.search(nearby):
            findings.append(
                {
                    "severity": "Medium",
                    "issue": f'"{words[i]}" has no attached number within {window_words} words.',
                    "fix": "Attach a real figure, or cut the qualifier if none is defensible.",
                }
            )
    return ToolResult(passed=len(findings) == 0, findings=findings)
