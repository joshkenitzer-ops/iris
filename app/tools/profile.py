"""
The portable Iris Profile (spec section 7). One downloadable markdown
file, JSON payload embedded, checksummed. Substitutes for server-side
storage: V1 has no account persistence, so the user's registry,
dismissed findings, and package state travel in this file between
sessions rather than living on a server.

Three tools, one document format, deliberately split the way the spec
splits them: T-2.16 checks the file hasn't been truncated or corrupted
in transit, and only that. T-2.15 then checks the content that
survives integrity is actually shaped like a profile the harness
understands. Editing the file by hand doesn't trip either check, on
purpose, the registry constrains the model during tailoring, not the
user, who already owns the facts and could type a wrong number at
Master Build regardless of this file's format.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from typing import Any, Dict, List

from app.enforcement import EnforcementKind, ToolResult, tool
from app.session import CriticalNotDismissibleError, Finding, Session
from app.tools.audit import compute_content_signature

PROFILE_VERSION = 1
_CHECKSUM_RE = re.compile(r"Checksum:\s*([0-9a-f]{64})")
_JSON_BLOCK_RE = re.compile(r"```json\n(.*?)\n```", re.DOTALL)


def _build_payload(session: Session) -> Dict[str, Any]:
    return {
        "version": PROFILE_VERSION,
        "registry": [asdict(fact) for fact in session.registry.values()],
        "dismissed_findings": [
            {
                "tool_id": f.tool_id,
                "issue": f.issue,
                "content_signature": f.content_signature,
            }
            for f in session.findings
            if f.dismissed
        ],
        "master_fingerprint": session.master_fingerprint,
    }


@tool(
    id="T-2.14",
    name="export_iris_profile",
    description=(
        "Serializes the session's registry, dismissed findings, and "
        "master fingerprint into a single downloadable markdown file "
        "with an embedded JSON payload and checksum. One artifact, not "
        "several; the user already carries the master docx separately."
    ),
    kind=EnforcementKind.TOOL,
    input_schema={"type": "object", "properties": {}},
    needs_session=True,
)
def export_iris_profile(session: Session) -> ToolResult:
    payload = _build_payload(session)
    body = json.dumps(payload, indent=2, sort_keys=True)
    checksum = hashlib.sha256(body.encode("utf-8")).hexdigest()
    markdown = (
        "# Iris Profile\n\n"
        f"Checksum: {checksum}\n\n"
        f"```json\n{body}\n```\n"
    )
    return ToolResult(passed=True, data={"profile_markdown": markdown, "checksum": checksum})


@tool(
    id="T-2.16",
    name="check_profile_integrity",
    description=(
        "Verifies a profile file's embedded checksum matches its JSON "
        "body. Guards against truncation and corruption in transit, "
        "not against the user editing values by hand, that is not what "
        "this check is for."
    ),
    kind=EnforcementKind.TOOL,
    input_schema={
        "type": "object",
        "properties": {"profile_markdown": {"type": "string"}},
        "required": ["profile_markdown"],
    },
)
def check_profile_integrity(profile_markdown: str) -> ToolResult:
    checksum_match = _CHECKSUM_RE.search(profile_markdown)
    json_match = _JSON_BLOCK_RE.search(profile_markdown)
    if not checksum_match or not json_match:
        return ToolResult(
            passed=False,
            findings=[
                {
                    "severity": "Critical",
                    "issue": "Profile file is missing its checksum line or JSON block.",
                    "fix": "Re-export a fresh profile; this file appears truncated.",
                }
            ],
        )
    body = json_match.group(1)
    actual = hashlib.sha256(body.encode("utf-8")).hexdigest()
    if actual != checksum_match.group(1):
        return ToolResult(
            passed=False,
            findings=[
                {
                    "severity": "Critical",
                    "issue": "Profile checksum does not match its content.",
                    "fix": "Re-export a fresh profile; this file was corrupted or partially transferred.",
                }
            ],
        )
    return ToolResult(passed=True, data={"json_body": body})


@tool(
    id="T-2.15",
    name="import_iris_profile",
    description=(
        "Parses and schema-validates a profile file after integrity "
        "has already been confirmed (T-2.16). Checks the version is "
        "supported and the payload has the expected top-level shape. "
        "Call check_profile_integrity first; this tool assumes a "
        "structurally intact file and validates its meaning, not its "
        "transport."
    ),
    kind=EnforcementKind.TOOL,
    input_schema={
        "type": "object",
        "properties": {"json_body": {"type": "string", "description": "The verified JSON body, from check_profile_integrity's output."}},
        "required": ["json_body"],
    },
)
def import_iris_profile(json_body: str) -> ToolResult:
    try:
        payload = json.loads(json_body)
    except json.JSONDecodeError as exc:
        return ToolResult(
            passed=False,
            findings=[{"severity": "Critical", "issue": f"Profile JSON failed to parse: {exc}", "fix": "Re-export a fresh profile."}],
        )

    if not isinstance(payload, dict) or "version" not in payload:
        return ToolResult(
            passed=False,
            findings=[{"severity": "Critical", "issue": "Profile payload is missing a version field.", "fix": "Re-export with a compatible harness version."}],
        )
    if payload["version"] != PROFILE_VERSION:
        return ToolResult(
            passed=False,
            findings=[
                {
                    "severity": "Critical",
                    "issue": f"Profile version {payload['version']} is not supported (expected {PROFILE_VERSION}).",
                    "fix": "Re-export with a compatible harness version.",
                }
            ],
        )
    missing_keys = [k for k in ("registry", "dismissed_findings") if k not in payload]
    if missing_keys:
        return ToolResult(
            passed=False,
            findings=[{"severity": "Critical", "issue": f"Profile payload missing key(s): {', '.join(missing_keys)}.", "fix": "Re-export a fresh profile."}],
        )
    return ToolResult(passed=True, data={"payload": payload})


@tool(
    id="T-2.18",
    name="apply_dismissed_findings",
    description=(
        "Applies a profile's dismissed_findings list onto the session, "
        "so a returning user does not see previously-cleared flags "
        "resurface. Matches by content signature; a finding whose "
        "underlying text has since changed will have a different "
        "signature and correctly reappears despite being in this list."
    ),
    kind=EnforcementKind.TOOL,
    input_schema={
        "type": "object",
        "properties": {
            "dismissed_findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "tool_id": {"type": "string"},
                        "issue": {"type": "string"},
                        "content_signature": {"type": "string"},
                    },
                    "required": ["tool_id", "issue"],
                },
            }
        },
        "required": ["dismissed_findings"],
    },
    needs_session=True,
)
def apply_dismissed_findings(dismissed_findings: List[dict], session: Session) -> ToolResult:
    applied = 0
    refused = []
    for entry in dismissed_findings:
        signature = entry.get("content_signature") or compute_content_signature(entry["tool_id"], entry["issue"])
        existing = next((f for f in session.findings if f.content_signature == signature), None)
        if existing is not None:
            try:
                existing.dismiss()
            except CriticalNotDismissibleError:
                # An imported profile carrying a Critical dismissal is
                # either corrupt or hostile. Refuse that entry, report
                # it, and keep importing the rest: one bad entry should
                # not discard a legitimate profile, and silence here
                # would hide exactly the case worth surfacing.
                refused.append(
                    {
                        "severity": "High",
                        "issue": (
                            f"Refused to dismiss Critical finding {existing.id} "
                            f"({existing.tool_id}) requested by the imported profile."
                        ),
                        "fix": "Criticals are resolved by fixing or dispositioning them, never by dismissal.",
                    }
                )
                continue
        else:
            session.findings.append(
                Finding(
                    id=f"imported-{signature}",
                    tool_id=entry["tool_id"],
                    severity="Unknown",  # export doesn't carry severity; this entry exists only to hold a dismissal
                    issue=entry["issue"],
                    fix="",
                    content_signature=signature,
                    dismissed=True,
                )
            )
        applied += 1
    return ToolResult(
        passed=len(refused) == 0,
        findings=refused,
        data={"applied_count": applied, "refused_count": len(refused)},
    )


@tool(
    id="T-2.17",
    name="check_facts_traceable_to_master",
    description=(
        "Given an uploaded master's text, checks that every active "
        "registry fact's value still appears in it. This is "
        "verification, not extraction: it confirms a rehydrated "
        "registry still traces to the master the user just uploaded, "
        "rather than attempting to re-derive facts from scratch via "
        "NLP, which the fact model treats as a Master Build step, not "
        "an automatic one."
    ),
    kind=EnforcementKind.TOOL,
    input_schema={
        "type": "object",
        "properties": {"master_text": {"type": "string"}},
        "required": ["master_text"],
    },
    needs_session=True,
)
def check_facts_traceable_to_master(master_text: str, session: Session) -> ToolResult:
    lowered = master_text.lower()
    findings = []
    for fact in session.active_facts():
        present = fact.value.lower() in lowered or any(v.lower() in lowered for v in fact.variants)
        if not present:
            findings.append(
                {
                    "severity": "Medium",
                    "issue": f"Registry fact '{fact.id}' (value '{fact.value}') was not found in the uploaded master.",
                    "fix": "Confirm this fact still applies, or mark it superseded if the master has changed.",
                }
            )
    return ToolResult(passed=len(findings) == 0, findings=findings)
