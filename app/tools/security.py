"""
T-3.15: custom term leak blocker.

Distinct from T-3.4 (check_user_defined_terms in app/tools/slop.py) in
consequence, not in matching logic. T-3.4 flags style: jargon and
retired terms that read poorly. This one is confidentiality: an
employer's internal codename or a term the user has explicitly marked
as never-repeat-this reaching output is a leak, not a style note, so
it is a GATE rather than a TOOL. Same shape of check, different
severity floor and blocking=True.
"""

from __future__ import annotations

from typing import List, Optional

from app.enforcement import EnforcementKind, ToolResult, tool


@tool(
    id="T-3.15",
    name="check_confidential_term_leak",
    description=(
        "Exact-match sweep for a user's confidential terms (employer "
        "codenames, internal project names) in generated output. Any "
        "occurrence not covered by an explicit allowlist entry is a "
        "hard stop, never judgment. Distinct from "
        "check_user_defined_terms (T-3.4), which is style guidance, "
        "not a leak."
    ),
    kind=EnforcementKind.GATE,
    input_schema={
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "blocked_terms": {
                "type": "array",
                "items": {"type": "string"},
                "description": "The user's confidential term list.",
            },
            "allowlist": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Terms explicitly cleared for public use despite matching a blocked term.",
            },
        },
        "required": ["text", "blocked_terms"],
    },
    blocking=True,
)
def check_confidential_term_leak(
    text: str, blocked_terms: List[str], allowlist: Optional[List[str]] = None
) -> ToolResult:
    allowlist_lower = {t.strip().lower() for t in (allowlist or [])}
    lowered = text.lower()
    findings = []
    for term in blocked_terms:
        term_clean = term.strip()
        term_lower = term_clean.lower()
        if not term_lower or term_lower in allowlist_lower:
            continue
        if term_lower in lowered:
            findings.append(
                {
                    "severity": "Critical",
                    "issue": f'Confidential term "{term_clean}" found in output.',
                    "fix": (
                        "Remove or replace with a plain, non-identifying "
                        "descriptor before this document can ship."
                    ),
                }
            )
    return ToolResult(passed=len(findings) == 0, findings=findings)
