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
from dataclasses import asdict, fields
from typing import Any, Dict, List

from app.enforcement import EnforcementKind, ToolResult, tool
from app.session import CriticalNotDismissibleError, Fact, Finding, Session
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
        "master fingerprint into a downloadable markdown file with an "
        "embedded JSON payload and checksum. Stores the file "
        "server-side and returns a file_id the user can download from "
        "the UI — the profile is used to restore full session state at "
        "the start of a future session, saving a full re-audit. The "
        "filename should follow the pattern "
        "[Last]_[First]_IrisProfile.md."
    ),
    kind=EnforcementKind.TOOL,
    input_schema={
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": "e.g. Kenitzer_Joshua_IrisProfile.md",
            }
        },
        "required": ["filename"],
    },
    needs_session=True,
)
def export_iris_profile(filename: str, session: Session) -> ToolResult:
    payload = _build_payload(session)
    body = json.dumps(payload, indent=2, sort_keys=True)
    checksum = hashlib.sha256(body.encode("utf-8")).hexdigest()
    markdown = (
        "# Iris Profile\n\n"
        f"Checksum: {checksum}\n\n"
        f"```json\n{body}\n```\n"
    )
    import base64 as _b64
    b64 = _b64.b64encode(markdown.encode("utf-8")).decode("ascii")
    rendered = session.add_rendered_file(
        filename=filename,
        content_type="text/markdown",
        data_base64=b64,
    )
    return ToolResult(
        passed=True,
        data={"file_id": rendered.id, "filename": rendered.filename, "checksum": checksum},
    )


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
        "transport. "
        "This VALIDATES ONLY and changes no session state. To actually "
        "restore the session, follow it with restore_registry_from_profile "
        "(T-2.19) for the facts and apply_dismissed_findings (T-2.18) for "
        "the dismissals; without those the session stays empty and T-5.2 "
        "blocks Fit Check."
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


_FACT_REQUIRED_FIELDS = ("id", "type", "value", "statement")
_FACT_FIELDS = {f.name for f in fields(Fact)}


@tool(
    id="T-2.19",
    name="restore_registry_from_profile",
    description=(
        "Writes a validated profile's Locked Facts Registry back onto "
        "the session. Call this after import_iris_profile (T-2.15), "
        "passing the payload's 'registry' list. Without it a returning "
        "user restores nothing usable: the registry stays empty, and "
        "T-5.2 blocks Fit Check and Tailoring. "
        "Refuses to overwrite a session that already has facts, so a "
        "profile import cannot silently discard work in progress. "
        "Restoring facts is not the same as verifying them: follow with "
        "check_facts_traceable_to_master (T-2.17) once the master is "
        "uploaded, which is what confirms a rehydrated registry still "
        "matches the document it came from."
    ),
    kind=EnforcementKind.TOOL,
    input_schema={
        "type": "object",
        "properties": {
            "registry": {
                "type": "array",
                "description": "The 'registry' list from import_iris_profile's validated payload.",
                "items": {"type": "object"},
            },
            "master_fingerprint": {
                "type": "string",
                "description": "The payload's 'master_fingerprint', if present. Restored alongside the facts.",
            },
        },
        "required": ["registry"],
    },
    needs_session=True,
)
def restore_registry_from_profile(registry: List[dict], session: Session, master_fingerprint: str = "") -> ToolResult:
    """The missing half of profile import.

    export_iris_profile has always serialized the registry, and
    import_iris_profile has always validated it and handed it back, but
    nothing ever wrote it onto the session: the only writer anywhere was
    registry_tools.lock_fact. So "pick up where I left off" restored
    dismissed findings and nothing else, and the tool description
    promising it saved "a full re-audit" was telling the model something
    untrue (found in the 2026-07-27 production readiness review).

    Facts arrive from a file the user holds, and the profile checksum
    guards transport rather than tampering, by design (see this module's
    docstring). That is deliberate, the user owns their own facts, and
    T-2.17 is the check that a restored registry still traces to a real
    master."""
    if session.active_facts():
        return ToolResult(
            passed=False,
            findings=[
                {
                    "severity": "High",
                    "issue": (
                        f"This session already has {len(session.active_facts())} active fact(s); "
                        "restoring a profile over them would discard work in progress."
                    ),
                    "fix": "Start a new session to restore this profile, or continue without importing.",
                }
            ],
        )

    restored, skipped = 0, []
    for entry in registry:
        if not isinstance(entry, dict):
            skipped.append({"severity": "Medium", "issue": f"Registry entry is {type(entry).__name__}, not an object.", "fix": "Re-export a fresh profile."})
            continue
        missing = [f for f in _FACT_REQUIRED_FIELDS if not str(entry.get(f, "")).strip()]
        if missing:
            skipped.append(
                {
                    "severity": "Medium",
                    "issue": f"Registry entry '{entry.get('id', '?')}' is missing required field(s): {', '.join(missing)}.",
                    "fix": "Re-export a fresh profile; this entry was dropped rather than restored partially.",
                }
            )
            continue
        # Ignore unknown keys rather than passing them to the constructor:
        # a profile written by a newer harness version should degrade to
        # the fields this one understands, not raise TypeError and lose
        # the whole import over one added field.
        session.registry[entry["id"]] = Fact(**{k: v for k, v in entry.items() if k in _FACT_FIELDS})
        restored += 1

    # The fingerprint travels in the same payload and is the other half
    # of "where I left off": without it T-2.19's own check
    # (check_profile_fingerprint) has nothing to compare a re-uploaded
    # master against.
    if master_fingerprint and master_fingerprint.strip():
        session.master_fingerprint = master_fingerprint.strip()

    return ToolResult(
        passed=len(skipped) == 0,
        findings=skipped,
        data={
            "restored_count": restored,
            "skipped_count": len(skipped),
            "master_fingerprint_restored": bool(master_fingerprint and master_fingerprint.strip()),
        },
    )


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
