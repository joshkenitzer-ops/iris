"""
T-0.9: primary-source verification of an existing claim.

Per the standing convention this encodes: absence of a claim's
distinctive tokens in the source means treat it as suspect and ask,
never resolve it automatically in either direction. This tool only
nominates; it has no findings severity above Medium and no path that
concludes a claim is confirmed true, only that its tokens were or
weren't found. That asymmetry is deliberate: presence of tokens is
weak evidence of support, absence is a real signal worth surfacing.
"""

from __future__ import annotations

import re

from app.enforcement import EnforcementKind, ToolResult, tool

_TOKEN_RE = re.compile(
    r"\d[\d,]*(?:\.\d+)?"  # numbers
    r"|\b[A-Z]{2,}\b"  # all-caps acronyms, two or more letters (AHT, ACM)
    r"|[A-Z][a-z]+(?:\s[A-Z][a-z]+)+"  # multi-word Title Case phrases (Southeast Asia)
)
# Deliberately excludes a lone Title Case word: at claim-start or after a
# period, an ordinary word ("Led", "Reduced") is capitalized by sentence
# position, not because it's a proper noun, and treating it as a
# distinctive token produced constant false negatives.


@tool(
    id="T-0.9",
    name="check_primary_source_support",
    description=(
        "Extracts distinctive tokens (numbers, capitalized multi-word "
        "phrases) from a claim and checks whether each appears in the "
        "provided source text. Returns which tokens are missing. Does "
        "not conclude the claim is false or unsupported outright, "
        "absence means treat it as suspect and ask the user, per "
        "standing convention; presence is weak evidence at best."
    ),
    kind=EnforcementKind.HYBRID,
    input_schema={
        "type": "object",
        "properties": {
            "claim_text": {"type": "string"},
            "source_text": {"type": "string"},
        },
        "required": ["claim_text", "source_text"],
    },
)
def check_primary_source_support(claim_text: str, source_text: str) -> ToolResult:
    tokens = sorted({m.group(0) for m in _TOKEN_RE.finditer(claim_text)})
    lowered_source = source_text.lower()
    missing = [t for t in tokens if t.lower() not in lowered_source]

    findings = [
        {
            "severity": "Medium",
            "issue": f"Token '{token}' from the claim was not found in the source text.",
            "fix": "Treat as suspect and ask the user; do not resolve automatically in either direction.",
        }
        for token in missing
    ]
    return ToolResult(passed=len(missing) == 0, findings=findings, data={"checked_tokens": tokens, "missing_tokens": missing})
