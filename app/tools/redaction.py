"""
T-0.4: colleague-name replacement with generic labels.

Tool-list split: detecting that a span of text names a colleague is
HYBRID, model judgment nominates candidates, a human confirms.
Performing the substitution once names are identified, and verifying
none leaked through, is deterministic, and that is what this module
does. It never decides who counts as a colleague; it takes a list of
already-identified names and makes the edit auditable.

Ordering matters: names are substituted longest-first, so a compound
name ("Jane Smith") is replaced whole before a shorter name that
happens to be a substring of it ("Jane") gets a chance to fragment it
into "Colleague A Smith", which would leave "Smith" exposed and the
leftover check blind to it, since "Jane Smith" would no longer appear
verbatim to catch.
"""

from __future__ import annotations

import re
from typing import Dict, List

from app.enforcement import EnforcementKind, ToolResult, tool


@tool(
    id="T-0.4",
    name="redact_colleague_names",
    description=(
        "Substitutes each name in identified_names with a generic "
        "label (Colleague A, Colleague B, ...) assigned by first "
        "appearance, then re-scans the result and fails if any "
        "identified name is still present verbatim. Storage is "
        "blocked until this passes clean; this tool does not decide "
        "who counts as a colleague, only performs and verifies the "
        "substitution once told."
    ),
    kind=EnforcementKind.GATE,
    input_schema={
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "identified_names": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Names already identified as colleagues, longest-first ordering is applied internally.",
            },
        },
        "required": ["text", "identified_names"],
    },
    blocking=True,
)
def redact_colleague_names(text: str, identified_names: List[str]) -> ToolResult:
    ordered_unique = sorted(dict.fromkeys(identified_names), key=len, reverse=True)
    label_map: Dict[str, str] = {}
    redacted = text

    for i, name in enumerate(ordered_unique):
        label = f"Colleague {chr(65 + i)}"
        label_map[name] = label
        pattern = re.compile(re.escape(name), re.IGNORECASE)
        redacted = pattern.sub(label, redacted)

    leftover = [name for name in identified_names if re.search(re.escape(name), redacted, re.IGNORECASE)]
    passed = len(leftover) == 0

    findings = (
        []
        if passed
        else [
            {
                "severity": "Critical",
                "issue": f"Name(s) still present after redaction attempt: {', '.join(leftover)}.",
                "fix": "Check for a name appearing with different spelling or punctuation than identified_names supplied.",
            }
        ]
    )
    return ToolResult(passed=passed, findings=findings, data={"redacted_text": redacted, "label_map": label_map})
