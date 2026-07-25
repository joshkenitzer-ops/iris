"""Phase 2 Master Build tools. See docs/iris-spec.md section 6, Phase 2."""

from __future__ import annotations

import re
from typing import List

from app.enforcement import EnforcementKind, ToolResult, tool
from app.gates import GateBlocked
from app.session import Session

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


@tool(
    id="T-2.4",
    name="check_role_summary_length",
    description="Checks a role summary is one to two sentences, no more.",
    kind=EnforcementKind.TOOL,
    input_schema={
        "type": "object",
        "properties": {"summary_text": {"type": "string"}},
        "required": ["summary_text"],
    },
)
def check_role_summary_length(summary_text: str) -> ToolResult:
    text = summary_text.strip()
    if not text:
        return ToolResult(
            passed=False,
            findings=[{"severity": "Medium", "issue": "Role summary is empty.", "fix": "Write one to two sentences."}],
        )
    sentences = [s for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]
    count = len(sentences)
    if 1 <= count <= 2:
        return ToolResult(passed=True, data={"sentence_count": count})
    return ToolResult(
        passed=False,
        data={"sentence_count": count},
        findings=[
            {
                "severity": "Medium",
                "issue": f"Role summary is {count} sentences; the spec calls for one to two.",
                "fix": "Trim to one or two sentences.",
            }
        ],
    )


@tool(
    id="T-2.7",
    name="check_headline_skills_backed",
    description=(
        "Checks that every skill listed in HEADLINE already exists in "
        "the Locked Facts Registry as an active skill-type fact. This "
        "is the cheapest anti-fabrication check in the system: a skill "
        "cannot appear in HEADLINE unless it was already approved "
        "somewhere else first."
    ),
    kind=EnforcementKind.TOOL,
    input_schema={
        "type": "object",
        "properties": {
            "headline_skills": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["headline_skills"],
    },
    needs_session=True,
)
def check_headline_skills_backed(headline_skills: List[str], session: Session) -> ToolResult:
    registry_skills = set()
    for fact in session.active_facts():
        if fact.type == "skill":
            registry_skills.add(fact.value.lower())
            registry_skills.update(v.lower() for v in fact.variants)

    unbacked = [s for s in headline_skills if s.lower() not in registry_skills]
    findings = [
        {
            "severity": "Critical",
            "issue": f"HEADLINE skill '{skill}' has no matching active fact in the registry.",
            "fix": "Add it to the registry through Master Build first, or remove it from HEADLINE.",
        }
        for skill in unbacked
    ]
    return ToolResult(passed=len(unbacked) == 0, findings=findings, data={"unbacked_skills": unbacked})


@tool(
    id="T-2.8",
    name="check_headline_placement",
    description="Checks HEADLINE appears after NAME and before CONTACT in the rendered section order.",
    kind=EnforcementKind.TOOL,
    input_schema={
        "type": "object",
        "properties": {
            "section_order": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Section names in the order they'll render, e.g. ['NAME', 'HEADLINE', 'CONTACT', ...].",
            }
        },
        "required": ["section_order"],
    },
)
def check_headline_placement(section_order: List[str]) -> ToolResult:
    try:
        name_i = section_order.index("NAME")
        headline_i = section_order.index("HEADLINE")
        contact_i = section_order.index("CONTACT")
    except ValueError as exc:
        return ToolResult(
            passed=False,
            findings=[{"severity": "Critical", "issue": f"Missing required section in order list: {exc}", "fix": "Include NAME, HEADLINE, and CONTACT."}],
        )
    if name_i < headline_i < contact_i:
        return ToolResult(passed=True)
    return ToolResult(
        passed=False,
        findings=[
            {
                "severity": "High",
                "issue": "HEADLINE is not positioned after NAME and before CONTACT.",
                "fix": "Move HEADLINE to sit directly between NAME and CONTACT.",
            }
        ],
    )


@tool(
    id="T-6.6",
    name="check_summary_bullet_count",
    description=(
        "Checks a tailored SUMMARY has 3-5 bullets (v0.7 supersedes "
        "the earlier paragraph form). Content quality and relevance "
        "are judgment; this only counts non-empty bullets."
    ),
    kind=EnforcementKind.TOOL,
    input_schema={
        "type": "object",
        "properties": {"bullets": {"type": "array", "items": {"type": "string"}}},
        "required": ["bullets"],
    },
)
def check_summary_bullet_count(bullets: List[str]) -> ToolResult:
    count = len([b for b in bullets if b.strip()])
    if 3 <= count <= 5:
        return ToolResult(passed=True, data={"bullet_count": count})
    return ToolResult(
        passed=False,
        data={"bullet_count": count},
        findings=[
            {
                "severity": "Medium",
                "issue": f"SUMMARY has {count} bullet(s); v0.7 calls for 3-5.",
                "fix": "Trim or expand to land between 3 and 5 bullets.",
            }
        ],
    )


@tool(
    id="T-6.7",
    name="check_headline_title_match",
    description=(
        "Checks a tailored HEADLINE contains the exact posting title "
        "text, case-insensitive. Skill selection is judgment and skill "
        "registry-membership is check_headline_skills_backed (T-2.7); "
        "this tool covers only the exact-title half of T-6.7."
    ),
    kind=EnforcementKind.TOOL,
    input_schema={
        "type": "object",
        "properties": {
            "headline_text": {"type": "string"},
            "posting_title": {"type": "string"},
        },
        "required": ["headline_text", "posting_title"],
    },
)
def check_headline_title_match(headline_text: str, posting_title: str) -> ToolResult:
    title = posting_title.strip()
    if not title:
        return ToolResult(
            passed=False,
            findings=[{"severity": "Medium", "issue": "No posting title supplied to match against.", "fix": "Provide the exact posting title from the JD."}],
        )
    if title.lower() in headline_text.strip().lower():
        return ToolResult(passed=True)
    return ToolResult(
        passed=False,
        findings=[
            {
                "severity": "Medium",
                "issue": f"HEADLINE does not contain the exact posting title '{title}'.",
                "fix": "Include the exact posting title text in the HEADLINE.",
            }
        ],
    )


def require_value_immutable(session: Session, fact_id: str, proposed_value: str) -> None:
    """T-2.9a: guards the registry's write path, not its output. An
    attempt to overwrite an active fact's value in place is blocked;
    a correction has to go through the supersede flow (spec 5.5) so
    the old value stays visible in history rather than disappearing.
    A brand-new fact_id is not affected, this only fires on existing
    active facts."""
    existing = session.registry.get(fact_id)
    if existing is None or existing.status != "active":
        return  # new fact or already-superseded slot; nothing to protect
    if existing.value != proposed_value and proposed_value not in existing.variants:
        raise GateBlocked(
            "T-2.9a",
            f"Fact '{fact_id}' is active with value '{existing.value}'. "
            f"Direct overwrite to '{proposed_value}' is blocked; use the "
            f"supersede flow so the prior value remains in history.",
        )


@tool(
    id="T-2.11",
    name="detect_internal_project_names",
    description=(
        "Nominates text spans matching a known internal-name list for a "
        "plain-English descriptor prompt during Master Build. "
        "Informational, not a block, unlike the T-3.15 leak gate that "
        "runs later at delivery against the same kind of list."
    ),
    kind=EnforcementKind.TOOL,
    input_schema={
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "known_internal_names": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["text", "known_internal_names"],
    },
)
def detect_internal_project_names(text: str, known_internal_names: List[str]) -> ToolResult:
    lowered = text.lower()
    found = [name for name in known_internal_names if name.strip() and name.strip().lower() in lowered]
    findings = [
        {
            "severity": "Low",
            "issue": f"Internal name '{name}' detected with no plain-English descriptor nearby.",
            "fix": "Prompt for a plain descriptor on first use in this document.",
        }
        for name in found
    ]
    return ToolResult(passed=len(found) == 0, findings=findings, data={"detected_names": found})


@tool(
    id="T-2.2",
    name="check_bold_lead_structure",
    description=(
        "Checks a bullet's intended bold-lead span is 3-6 words. This "
        "checks word count only; whether the span actually renders "
        "bold in the docx is a separate check that runs at docx render "
        "time (T-4.8), once that layer exists."
    ),
    kind=EnforcementKind.TOOL,
    input_schema={
        "type": "object",
        "properties": {"lead_text": {"type": "string"}},
        "required": ["lead_text"],
    },
)
def check_bold_lead_structure(lead_text: str) -> ToolResult:
    word_count = len(lead_text.split())
    if 3 <= word_count <= 6:
        return ToolResult(passed=True, data={"word_count": word_count})
    return ToolResult(
        passed=False,
        data={"word_count": word_count},
        findings=[
            {
                "severity": "Medium",
                "issue": f"Bold-lead span is {word_count} words; the spec calls for 3-6.",
                "fix": "Tighten or expand the lead phrase to land in range.",
            }
        ],
    )


@tool(
    id="T-2.13",
    name="get_open_audit_findings_for_section",
    description=(
        "Returns open (not dismissed) findings tagged to a given "
        "careerInventory section, for surfacing as a prompt while the "
        "user works on that section during Master Build."
    ),
    kind=EnforcementKind.TOOL,
    input_schema={
        "type": "object",
        "properties": {"section": {"type": "string"}},
        "required": ["section"],
    },
    needs_session=True,
)
def get_open_audit_findings_for_section(section: str, session: Session) -> ToolResult:
    matching = [f for f in session.findings if f.section == section and not f.dismissed]
    findings = [{"severity": f.severity, "issue": f.issue, "fix": f.fix} for f in matching]
    return ToolResult(passed=len(matching) == 0, findings=findings, data={"open_count": len(matching)})
