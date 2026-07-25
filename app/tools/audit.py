"""
T-1.7: findings carry-forward checklist.

The convention this encodes: a dismissal is keyed by what the finding
is about (a hash of its issue text plus the span it points at), never
by which run produced it. Revise the flagged text and the signature
changes, so the finding correctly reappears; leave it alone and a
dismissal from three sessions ago still holds. This is pure state
bookkeeping, no judgment involved, which is why it's a TOOL rather
than anything softer.
"""

from __future__ import annotations

import hashlib
from typing import List

from app.enforcement import EnforcementKind, ToolResult, tool
from app.session import Finding, Session


def compute_content_signature(tool_id: str, issue_text: str) -> str:
    """Deterministic signature for a finding. Same tool + same issue
    text -> same signature, regardless of which session or run produced
    it. This is a plain function, not a registered tool, because it's
    a building block other tools call rather than something Claude
    needs to invoke on its own."""
    raw = f"{tool_id}::{issue_text}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


@tool(
    id="T-1.7",
    name="filter_carried_forward_findings",
    description=(
        "Given a fresh batch of findings from re-running the audit, "
        "returns which ones are new versus already-known (by content "
        "signature) versus previously dismissed. Dismissed findings "
        "with a matching signature stay dismissed; anything with a new "
        "signature, including a revised version of previously flagged "
        "text, surfaces again."
    ),
    kind=EnforcementKind.TOOL,
    input_schema={
        "type": "object",
        "properties": {
            "new_findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "tool_id": {"type": "string"},
                        "issue": {"type": "string"},
                        "severity": {"type": "string"},
                        "fix": {"type": "string"},
                    },
                    "required": ["tool_id", "issue", "severity", "fix"],
                },
            }
        },
        "required": ["new_findings"],
    },
    needs_session=True,
)
def filter_carried_forward_findings(new_findings: List[dict], session: Session) -> ToolResult:
    dismissed_signatures = {f.content_signature for f in session.findings if f.dismissed and f.content_signature}

    surfaced = []
    already_dismissed = []
    for finding in new_findings:
        signature = compute_content_signature(finding["tool_id"], finding["issue"])
        if signature in dismissed_signatures:
            already_dismissed.append({**finding, "content_signature": signature})
        else:
            surfaced.append({**finding, "content_signature": signature})

    return ToolResult(
        passed=True,  # informational; this tool sorts findings, it doesn't gate anything
        data={"surfaced": surfaced, "already_dismissed": already_dismissed},
    )
