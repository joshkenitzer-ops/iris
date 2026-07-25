"""
Locked Facts Registry tools (spec section 5, tool list section 16).

Both tools here are needs_session=True. The registry they check
against comes from the authenticated session the harness already
resolved, never from the model's tool_input. Without this, a model
could pass its own fabricated "active_facts" list alongside a claim
and the check would agree with whatever it was handed. See
app/enforcement.py's dispatch() docstring for why this is structural
rather than a naming convention.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from app.enforcement import EnforcementKind, ToolResult, tool
from app.session import Fact, LimitOverride, Session

_FACT_ID_RE = re.compile(r"^F-(\d+)$")


def _next_fact_id(session: Session) -> str:
    """Generates the next sequential fact id. Scans every id currently
    in the registry, including superseded ones (which stay per
    T-2.9a), rather than using len(registry): once any fact has been
    superseded, a successor already occupies a slot that len() would
    not account for, and reusing a number would collide with history
    that must stay distinguishable."""
    max_n = 0
    for fid in session.registry:
        match = _FACT_ID_RE.match(fid)
        if match:
            max_n = max(max_n, int(match.group(1)))
    return f"F-{max_n + 1:03d}"


@tool(
    id="T-2.10",
    name="validate_facts_for_locking",
    description=(
        "Validates a batch of extracted facts before they lock into "
        "the registry on section approval. Checks required fields per "
        "fact type (spec 5.2, 5.3) and rejects a batch where any fact "
        "is missing its value or statement. Locking itself is a "
        "session-state write the harness performs after this passes; "
        "this tool only validates shape."
    ),
    kind=EnforcementKind.TOOL,
    input_schema={
        "type": "object",
        "properties": {
            "facts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {
                            "type": "string",
                            "enum": ["metric", "date_span", "entity", "claim", "skill", "phrasing_lock"],
                        },
                        "value": {"type": "string"},
                        "statement": {"type": "string"},
                        "source": {"type": "string"},
                        "role_ref": {"type": "string"},
                    },
                    "required": ["type", "value", "statement"],
                },
            }
        },
        "required": ["facts"],
    },
)
def validate_facts_for_locking(facts: List[Dict[str, Any]]) -> ToolResult:
    findings = []
    for i, fact in enumerate(facts):
        missing = [k for k in ("type", "value", "statement") if not fact.get(k)]
        if missing:
            findings.append(
                {
                    "severity": "Critical",
                    "issue": f"Fact at index {i} missing required field(s): {', '.join(missing)}.",
                    "fix": "Supply every required field before this batch can lock.",
                }
            )
    return ToolResult(passed=len(findings) == 0, findings=findings, data={"fact_count": len(facts)})


@tool(
    id="T-2.9",
    name="extract_facts_into_registry",
    description=(
        "Writes a batch of already-typed facts, already shape-checked "
        "by validate_facts_for_locking (T-2.10), into the session's "
        "Locked Facts Registry, assigning each a sequential id when "
        "none is supplied. Typing, storage, and indexing are the "
        "deterministic half of T-2.9; the granularity call, deciding "
        "where one assertion ends and the next begins, is judgment "
        "that has to happen before this tool is ever invoked, not "
        "inside it. If a fact's 'id' names an existing active fact, "
        "T-2.9a's write-once rule applies: a value change is blocked "
        "here rather than silently overwritten, and that fact is "
        "skipped with a Critical finding rather than failing the "
        "whole batch."
    ),
    kind=EnforcementKind.HYBRID,
    input_schema={
        "type": "object",
        "properties": {
            "facts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "string",
                            "description": "Existing fact id to update; omit to create a new fact.",
                        },
                        "type": {
                            "type": "string",
                            "enum": ["metric", "date_span", "entity", "claim", "skill", "phrasing_lock"],
                        },
                        "value": {"type": "string"},
                        "statement": {"type": "string"},
                        "source": {"type": "string"},
                        "role_ref": {"type": "string"},
                        "co_occurs_with": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["type", "value", "statement"],
                },
            }
        },
        "required": ["facts"],
    },
    needs_session=True,
)
def extract_facts_into_registry(facts: List[Dict[str, Any]], session: Session) -> ToolResult:
    from app.gates import GateBlocked
    from app.tools.master_build import require_value_immutable

    shape_check = validate_facts_for_locking(facts)
    if not shape_check.passed:
        return shape_check

    created_ids: List[str] = []
    findings: List[Dict[str, Any]] = []
    for fact_dict in facts:
        fact_id = fact_dict.get("id")
        if fact_id:
            try:
                require_value_immutable(session, fact_id, fact_dict["value"])
            except GateBlocked as exc:
                findings.append(
                    {
                        "severity": "Critical",
                        "issue": exc.message,
                        "fix": "Use the supersede flow for a correction; this batch did not write that fact.",
                    }
                )
                continue
        else:
            fact_id = _next_fact_id(session)

        session.registry[fact_id] = Fact(
            id=fact_id,
            type=fact_dict["type"],
            value=fact_dict["value"],
            statement=fact_dict["statement"],
            source=fact_dict.get("source"),
            role_ref=fact_dict.get("role_ref"),
            co_occurs_with=fact_dict.get("co_occurs_with", []),
        )
        created_ids.append(fact_id)

    return ToolResult(passed=len(findings) == 0, findings=findings, data={"fact_ids": created_ids})


@tool(
    id="T-8.2",
    name="check_value_against_registry",
    description=(
        "Checks a claimed value in generated text against its locked "
        "registry entry. An altered value is Critical severity even "
        "when it sounds plausible; that is the entire point of this "
        "check, a model reading a plausible wrong figure would "
        "otherwise accept it. Compares against the authenticated "
        "session's registry, never against a fact set supplied in the "
        "call."
    ),
    kind=EnforcementKind.TOOL,
    input_schema={
        "type": "object",
        "properties": {
            "fact_id": {"type": "string", "description": "Registry fact id, e.g. 'F-014'."},
            "claimed_value": {"type": "string", "description": "The value as it appears in the draft."},
        },
        "required": ["fact_id", "claimed_value"],
    },
    needs_session=True,
)
def check_value_against_registry(fact_id: str, claimed_value: str, session: Session) -> ToolResult:
    fact: Fact | None = session.registry.get(fact_id)
    if fact is None:
        return ToolResult(
            passed=False,
            findings=[
                {
                    "severity": "Critical",
                    "issue": f"No registry entry for fact id '{fact_id}'.",
                    "fix": "Cite an existing fact id, or add this as a new fact through Master Build first.",
                }
            ],
        )
    if fact.status != "active":
        return ToolResult(
            passed=False,
            findings=[
                {
                    "severity": "Critical",
                    "issue": f"Fact '{fact_id}' is superseded, not active.",
                    "fix": f"Use its successor fact instead (supersedes chain: {fact.supersedes}).",
                }
            ],
        )
    if claimed_value == fact.value or claimed_value in fact.variants:
        return ToolResult(passed=True)
    return ToolResult(
        passed=False,
        findings=[
            {
                "severity": "Critical",
                "issue": (
                    f"Claimed value '{claimed_value}' does not match locked "
                    f"value '{fact.value}' for fact '{fact_id}'."
                ),
                "fix": (
                    "Use the exact locked value, or an approved variant. "
                    "A new variant requires explicit user approval (spec 5.4) "
                    "before this check will accept it."
                ),
            }
        ],
    )


@tool(
    id="T-8.21",
    name="record_limit_override",
    description=(
        "Records a per-instance authorization to exceed a default "
        "limit (bullet word count, cover letter length) with a stated "
        "rationale. Distinct from a config change: this covers exactly "
        "one artifact, never raises the ceiling for anything else. "
        "Without this record, an authorized exception and an "
        "unnoticed violation look identical."
    ),
    kind=EnforcementKind.TOOL,
    input_schema={
        "type": "object",
        "properties": {
            "limit_id": {"type": "string", "description": "e.g. 'T-8.7' or 'T-7.13'."},
            "artifact_ref": {"type": "string", "description": "Which bullet, letter, or document this covers."},
            "rationale": {"type": "string"},
        },
        "required": ["limit_id", "artifact_ref", "rationale"],
    },
    needs_session=True,
)
def record_limit_override(limit_id: str, artifact_ref: str, rationale: str, session: Session) -> ToolResult:
    override = LimitOverride(limit_id=limit_id, artifact_ref=artifact_ref, rationale=rationale)
    session.limit_overrides.append(override)
    return ToolResult(passed=True, data={"recorded_at": override.recorded_at})


@tool(
    id="T-9.2",
    name="get_inventory_section_facts",
    description=(
        "Retrieves only the active facts belonging to one "
        "careerInventory section (matched by role_ref or type), rather "
        "than the whole registry. One tool call per section beats "
        "loading every section on every request."
    ),
    kind=EnforcementKind.TOOL,
    input_schema={
        "type": "object",
        "properties": {
            "section": {"type": "string", "description": "A role_ref value, or a fact type name."},
        },
        "required": ["section"],
    },
    needs_session=True,
)
def get_inventory_section_facts(section: str, session: Session) -> ToolResult:
    matching = [
        fact
        for fact in session.active_facts()
        if fact.role_ref == section or fact.type == section
    ]
    data = [{"id": f.id, "type": f.type, "value": f.value, "statement": f.statement} for f in matching]
    return ToolResult(passed=True, data={"facts": data, "count": len(data)})
