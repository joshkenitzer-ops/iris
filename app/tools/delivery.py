"""
T-6.14: unresolved marker sweep.

This used to exist only inside app/gates.py as a function that
raises. It still does that, for the harness's own mandatory
server-side check, but the actual scanning logic now lives here, as a
registered tool the model can call on its own drafts before finalizing
them. app/gates.py imports check_unresolved_markers and calls it
directly rather than re-implementing the same regex, so there is one
place this rule is encoded, not two that could quietly drift apart
from each other.
"""

from __future__ import annotations

from app.enforcement import EnforcementKind, ToolResult, tool

MARKER_PREFIX = "[ADD METRIC:"


@tool(
    id="T-6.14",
    name="check_unresolved_markers",
    description=(
        "Scans text for an unresolved [ADD METRIC: ...] marker. No "
        "document ships with one present. Call this on a draft before "
        "considering it final; app/gates.py calls the same underlying "
        "logic again, unconditionally, at the delivery boundary."
    ),
    kind=EnforcementKind.GATE,
    input_schema={
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    },
    blocking=True,
)
def check_unresolved_markers(text: str) -> ToolResult:
    count = text.count(MARKER_PREFIX)
    if count == 0:
        return ToolResult(passed=True)
    return ToolResult(
        passed=False,
        findings=[
            {
                "severity": "Critical",
                "issue": f"{count} unresolved [ADD METRIC: ...] marker(s) found.",
                "fix": "Resolve each with a real figure from the registry, or cut the claim.",
            }
        ],
    )
