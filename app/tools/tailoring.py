"""
T-6.8: flag JD phrases with no verbatim match.

Deliberately dumb by design. Deciding which phrases from a job
description matter is judgment (spec Phase 6: "extract the five to
six most important requirements"), and that happens elsewhere, by a
model, before this tool ever runs. This tool's only job is the part
that must never be judgment: given a phrase list someone already
decided matters, which of them appear verbatim in the tailored text,
case-insensitive. The output is informational. Nothing here inserts a
phrase into anything; T-6.9 (never auto-insert) is a gate specifically
against that, enforced by simply not giving this tool a write path.
"""

from __future__ import annotations

import hashlib
import re
from typing import Dict, List, Optional

from app.enforcement import EnforcementKind, ToolResult, tool
from app.untrusted_text import wrap_untrusted
from app.session import Session


@tool(
    id="T-6.1",
    name="ingest_job_description",
    description=(
        "Ingests a pasted job description for Fit Check and Tailoring. "
        "Only pasted text is in V1 scope; URL scrape is post-V1 per the "
        "tool list, not attempted here. Resets fit_check_completed and "
        "fit_check_gaps for this submission, since T-5.1 requires Fit "
        "Check to run again on every new JD, not just the first one."
    ),
    kind=EnforcementKind.TOOL,
    input_schema={
        "type": "object",
        "properties": {"jd_text": {"type": "string"}},
        "required": ["jd_text"],
    },
    needs_session=True,
)
def ingest_job_description(jd_text: str, session: Session) -> ToolResult:
    text = jd_text.strip()
    if not text:
        return ToolResult(
            passed=False,
            findings=[
                {
                    "severity": "High",
                    "issue": "Job description text is empty.",
                    "fix": "Paste the full job description text before continuing.",
                }
            ],
        )
    session.jd_text = text
    session.jd_fingerprint = hashlib.sha256(text.encode("utf-8")).hexdigest()
    session.fit_check_completed = False
    session.fit_check_gaps = []
    session.gap_acknowledgments = {}
    return ToolResult(
        passed=True,
        data={
            "jd_text": wrap_untrusted(text, "pasted job description"),
            "jd_fingerprint": session.jd_fingerprint,
            "char_count": len(text),
        },
    )


def record_gap_acknowledgment(gap: str, reason: str, session: Session) -> None:
    """Plain helper, not a registered tool: backs the T-7.8 gate in
    app.gates (require_gap_not_silently_removed), the same pattern as
    flag_pending_amendment/clear_pending_amendment in
    app.tools.harness_meta. The gate needs a place a human decision
    actually lands before it can distinguish an authorized softening
    from a silent removal; this is that place. Call only after the
    user has actually confirmed softening or removing a flagged gap,
    never speculatively on the model's own judgment that it's fine."""
    session.gap_acknowledgments[gap] = reason


@tool(
    id="T-6.8",
    name="check_jd_phrase_coverage",
    description=(
        "Given a list of notable JD phrases and the tailored resume "
        "text, returns which phrases have no verbatim (case-insensitive) "
        "match anywhere in the text. Informational only; the harness "
        "never auto-inserts a missing phrase (T-6.9), the user decides "
        "per phrase."
    ),
    kind=EnforcementKind.TOOL,
    input_schema={
        "type": "object",
        "properties": {
            "jd_phrases": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Phrases already judged important enough to check for.",
            },
            "resume_text": {"type": "string"},
        },
        "required": ["jd_phrases", "resume_text"],
    },
    needs_session=True,
)
def check_jd_phrase_coverage(jd_phrases: List[str], resume_text: str, session: Session) -> ToolResult:
    """Also records that the Fit Check ran for this submission.

    session.fit_check_completed is a DERIVED fact, never an assertion.
    T-5.1 requires a Fit Check before Tailoring, every time; until
    2026-07-28 nothing in the codebase ever set that flag to True, so
    the gate could not be enforced without permanently blocking
    Tailoring.

    The obvious fix, a "record_fit_check_complete" tool the model
    calls, is exactly the model self-report spec rule 4.1 refuses to
    accept as enforcement: it would let the model claim a Fit Check it
    never ran. Setting it here instead means the flag can only become
    True as a side effect of the deterministic JD-to-resume comparison
    actually executing. The model cannot assert the Fit Check happened.
    It happens, and the harness notices.

    ingest_job_description resets this to False on every new JD (see
    T-6.1 below), so a stale pass cannot satisfy a later submission."""
    session.fit_check_completed = True
    lowered_resume = resume_text.lower()
    missing = [phrase for phrase in jd_phrases if phrase.strip().lower() not in lowered_resume]
    findings = [
        {
            "severity": "Low",
            "issue": f'JD phrase "{phrase}" has no verbatim match in the tailored resume.',
            "fix": "Informational. Swap in the exact phrase only if it fits honestly; do not auto-insert.",
        }
        for phrase in missing
    ]
    return ToolResult(passed=len(missing) == 0, findings=findings, data={"missing_phrases": missing})


@tool(
    id="T-6.10",
    name="replace_internal_names",
    description=(
        "Replaces each internal/codename term with its plain-English "
        "descriptor in tailored output, longest term first so a "
        "compound name is swapped whole before a substring of it can "
        "fragment the replacement. Fails if any term is still present "
        "after substitution, the same leftover-check pattern used for "
        "colleague-name redaction (T-0.4)."
    ),
    kind=EnforcementKind.TOOL,
    input_schema={
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "term_replacements": {
                "type": "object",
                "description": "Map of internal term -> plain-English descriptor.",
                "additionalProperties": {"type": "string"},
            },
        },
        "required": ["text", "term_replacements"],
    },
)
def replace_internal_names(text: str, term_replacements: Dict[str, str]) -> ToolResult:
    result = text
    for term in sorted(term_replacements, key=len, reverse=True):
        pattern = re.compile(re.escape(term), re.IGNORECASE)
        result = pattern.sub(term_replacements[term], result)

    unresolved = [term for term in term_replacements if re.search(re.escape(term), result, re.IGNORECASE)]
    passed = len(unresolved) == 0
    findings = (
        []
        if passed
        else [
            {
                "severity": "Critical",
                "issue": f"Internal term(s) still present after replacement: {', '.join(unresolved)}.",
                "fix": "Check for a spelling or casing variant not covered by term_replacements.",
            }
        ]
    )
    return ToolResult(passed=passed, findings=findings, data={"replaced_text": result, "unresolved_terms": unresolved})


@tool(
    id="T-6.15",
    name="get_fit_check_gaps_for_cover_letter",
    description=(
        "Returns the gaps identified during Fit Check so the cover "
        "letter phase can name them honestly. Pure state handoff, no "
        "judgment: the gaps were already identified in Phase 5, this "
        "just carries them into Phase 7."
    ),
    kind=EnforcementKind.TOOL,
    input_schema={"type": "object", "properties": {}},
    needs_session=True,
)
def get_fit_check_gaps_for_cover_letter(session: Session) -> ToolResult:
    return ToolResult(passed=True, data={"gaps": list(session.fit_check_gaps)})


@tool(
    id="T-6.9",
    name="check_no_unauthorized_phrase_insertion",
    description=(
        "Given a JD phrase flagged as missing (T-6.8) and the resume "
        "before and after a revision, fails if the phrase now appears "
        "in the revised text without having been explicitly confirmed "
        "by the user. Never auto-insert a flagged phrase means exactly "
        "this: the phrase's appearance must trace to a user decision, "
        "not a model deciding on its own."
    ),
    kind=EnforcementKind.GATE,
    input_schema={
        "type": "object",
        "properties": {
            "original_text": {"type": "string"},
            "revised_text": {"type": "string"},
            "flagged_phrases": {"type": "array", "items": {"type": "string"}},
            "user_confirmed_phrases": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["original_text", "revised_text", "flagged_phrases"],
    },
    blocking=True,
)
def check_no_unauthorized_phrase_insertion(
    original_text: str, revised_text: str, flagged_phrases: List[str], user_confirmed_phrases: Optional[List[str]] = None
) -> ToolResult:
    confirmed_lower = {p.strip().lower() for p in (user_confirmed_phrases or [])}
    original_lower = original_text.lower()
    revised_lower = revised_text.lower()

    findings = []
    for phrase in flagged_phrases:
        phrase_lower = phrase.strip().lower()
        newly_present = phrase_lower not in original_lower and phrase_lower in revised_lower
        if newly_present and phrase_lower not in confirmed_lower:
            findings.append(
                {
                    "severity": "Critical",
                    "issue": f"Flagged phrase '{phrase}' was inserted without user confirmation.",
                    "fix": "Remove it, or get explicit user confirmation for this specific phrase before it ships.",
                }
            )
    return ToolResult(passed=len(findings) == 0, findings=findings)


@tool(
    id="T-6.12",
    name="check_no_invention",
    description=(
        "Provenance-based no-invention check. Every span of generated "
        "content must carry a registry fact id. A span with no id, or "
        "an id absent from the active registry, fails; this is what "
        "makes no-invention a set operation instead of a heuristic "
        "(spec 5.8). User-authored spans are exempt (T-7.14) since "
        "they carry no fact id by definition and are not generated "
        "content."
    ),
    kind=EnforcementKind.GATE,
    input_schema={
        "type": "object",
        "properties": {
            "spans": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "fact_id": {"type": ["string", "null"]},
                        "user_authored": {"type": "boolean"},
                    },
                    "required": ["text"],
                },
            }
        },
        "required": ["spans"],
    },
    blocking=True,
    needs_session=True,
)
def check_no_invention(spans: List[dict], session: Session) -> ToolResult:
    findings = []
    for span in spans:
        if span.get("user_authored"):
            continue  # T-7.14: exempt by definition, not a provenance gap
        fact_id = span.get("fact_id")
        if not fact_id:
            findings.append(
                {
                    "severity": "Critical",
                    "issue": f"Span has no registry fact id: '{span['text'][:50]}'.",
                    "fix": "Trace this span to a registry fact, or mark it user-authored if the user wrote it directly.",
                }
            )
            continue
        fact = session.registry.get(fact_id)
        if fact is None or fact.status != "active":
            findings.append(
                {
                    "severity": "Critical",
                    "issue": f"Span cites fact id '{fact_id}', which is not an active registry entry: '{span['text'][:50]}'.",
                    "fix": "Cite an existing active fact, or add it through Foundational Build first.",
                }
            )
    return ToolResult(passed=len(findings) == 0, findings=findings)
