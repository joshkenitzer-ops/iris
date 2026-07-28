"""
Harness-level tools. These aren't about resume content, they're about
the amendment protocol and delivery bookkeeping the spec itself
describes in section 9.
"""

from __future__ import annotations

import difflib

from app.enforcement import EnforcementKind, ToolResult, tool
from app.session import Session


@tool(
    id="T-9.4",
    name="generate_amendment_diff",
    description=(
        "Generates a unified diff between the current spec text and a "
        "proposed revision. Per the amendment protocol, a proposed "
        "change is shown as an actual diff and committed only after "
        "explicit confirmation; this tool produces that diff, it does "
        "not decide the content of the change or apply it."
    ),
    kind=EnforcementKind.TOOL,
    input_schema={
        "type": "object",
        "properties": {
            "old_text": {"type": "string"},
            "new_text": {"type": "string"},
            "label": {"type": "string", "description": "e.g. the spec filename, for the diff header."},
        },
        "required": ["old_text", "new_text"],
    },
)
def generate_amendment_diff(old_text: str, new_text: str, label: str = "spec") -> ToolResult:
    diff_lines = list(
        difflib.unified_diff(
            old_text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile=f"{label} (current)",
            tofile=f"{label} (proposed)",
        )
    )
    diff_text = "".join(diff_lines)
    return ToolResult(passed=True, data={"diff": diff_text, "changed": len(diff_lines) > 0})


@tool(
    id="T-9.7",
    name="check_batch_state",
    description=(
        "Checks whether a new batch can start: the prior one must be "
        "closed first. A batch left open when a new one starts is a "
        "state bug, not a valid situation, so this fails loudly rather "
        "than silently opening a second concurrent batch."
    ),
    kind=EnforcementKind.TOOL,
    input_schema={
        "type": "object",
        "properties": {"new_batch_id": {"type": "string"}},
        "required": ["new_batch_id"],
    },
    needs_session=True,
)
def check_batch_state(new_batch_id: str, session: Session) -> ToolResult:
    if session.active_batch_id is not None and session.active_batch_id != new_batch_id:
        return ToolResult(
            passed=False,
            findings=[
                {
                    "severity": "High",
                    "issue": f"Batch '{session.active_batch_id}' is still open; cannot start '{new_batch_id}'.",
                    "fix": "Close the prior batch before starting a new one.",
                }
            ],
        )
    session.active_batch_id = new_batch_id
    return ToolResult(passed=True, data={"active_batch_id": session.active_batch_id})


def flag_pending_amendment(reason: str, session: Session) -> None:
    """Plain helper, not a registered tool: supports the T-9.6 gate in
    app/gates.py the same way compute_content_signature supports T-1.7
    without being its own tool-list item. Call the moment a
    rule-changing decision is made, before drafting the diff."""
    session.pending_amendment_reason = reason


def clear_pending_amendment(session: Session) -> None:
    """Clears the pending-amendment flag once the diff has actually
    been shown and committed. Call only after the real amendment
    lands, not before."""
    session.pending_amendment_reason = None


@tool(
    id="T-9.8",
    name="lock_package_version",
    description=(
        "Locks a submitted package's version. Once locked, "
        "regeneration increments the version rather than overwriting "
        "the file, per the filename convention (section 8)."
    ),
    kind=EnforcementKind.TOOL,
    input_schema={
        "type": "object",
        "properties": {"artifact_ref": {"type": "string"}},
        "required": ["artifact_ref"],
    },
    needs_session=True,
)
def lock_package_version(artifact_ref: str, session: Session) -> ToolResult:
    current = session.locked_package_versions.get(artifact_ref, 0)
    new_version = current + 1
    session.locked_package_versions[artifact_ref] = new_version
    return ToolResult(passed=True, data={"version": new_version})


@tool(
    id="T-9.9",
    name="generate_move_item_command",
    description=(
        "Generates the PowerShell Move-Item command for delivering a "
        "generated file from Downloads to its destination path, "
        "matching the convention used throughout this project."
    ),
    kind=EnforcementKind.TOOL,
    input_schema={
        "type": "object",
        "properties": {
            "filename": {"type": "string"},
            "destination_dir": {"type": "string", "description": "Relative or absolute destination directory."},
        },
        "required": ["filename", "destination_dir"],
    },
)
def generate_move_item_command(filename: str, destination_dir: str) -> ToolResult:
    destination = f"{destination_dir.rstrip(chr(92)).rstrip('/')}\\{filename}"
    command = f'Move-Item -Path "$HOME\\Downloads\\{filename}" -Destination "{destination}" -Force'
    return ToolResult(passed=True, data={"command": command})


@tool(
    id="T-9.16",
    name="advance_phase",
    description=(
        "Advances the session to a named pipeline phase. Call this when "
        "the current phase's work is genuinely finished, before starting "
        "the next one. The harness checks the gates that guard the "
        "transition and REFUSES the advance if any fails, so a phase "
        "cannot be entered on the strength of an assertion that its "
        "prerequisites were met. Valid targets: STARTING_POINT, AUDIT, "
        "FOUNDATIONAL_BUILD, SLOP_AUDIT, FORMATTING, FIT_CHECK, "
        "TAILORING, COVER_LETTER, FINAL_REVIEW."
    ),
    kind=EnforcementKind.GATE,
    input_schema={
        "type": "object",
        "properties": {
            "target_phase": {
                "type": "string",
                "description": "Phase name, e.g. FOUNDATIONAL_BUILD.",
            }
        },
        "required": ["target_phase"],
    },
    blocking=True,
    needs_session=True,
)
def advance_phase_tool(target_phase: str, session: Session) -> ToolResult:
    """T-9.16. Phase advancement, as a tool the model must invoke.

    Added 2026-07-28. The gates guarding phase transitions were written,
    tested, and correct, and lived only inside POST /advance-phase,
    which static/app.js never calls. Every session therefore sat in
    STARTING_POINT for its entire life and every gate hanging off a
    phase boundary was inert: require_phase1_disposition (T-1.8) never
    blocked a Foundational Build over an unresolved audit Critical, and
    require_registry_populated (T-5.2) never blocked a Fit Check on an
    empty registry. Both were shipped protections that had never once
    protected anyone.

    The division of labour here is the harness's core pattern rather
    than a convenience. The MODEL knows when a phase's work is done,
    which is judgment and cannot be computed. The HARNESS decides
    whether the advance is permitted, which is deterministic and must
    never be delegated. So the model asks, and code answers.

    Returns passed=False rather than raising, matching the delivery
    gate in docx_render: a raise becomes a generic "tool failed to run"
    that tells the model nothing it can act on, whereas a finding names
    the gate, says what is unresolved, and leaves the session exactly
    where it was. A refused advance is recoverable by doing the missing
    work, never a dead end."""
    from app.gates import (
        GateBlocked,
        require_fit_check_completed,
        require_phase1_disposition,
        require_registry_populated,
    )
    from app.session import Phase

    try:
        target = Phase[target_phase.strip().upper()]
    except KeyError:
        return ToolResult(
            passed=False,
            findings=[
                {
                    "severity": "High",
                    "issue": f"'{target_phase}' is not a phase name.",
                    "fix": "Use one of: " + ", ".join(p.name for p in Phase),
                }
            ],
        )

    previous = session.phase
    try:
        # Same checks, same order, as the /advance-phase route. Phase 8
        # is deliberately absent: it is gated on the way OUT, at
        # delivery, by require_no_open_criticals at the render
        # chokepoint, not on the way in.
        if target == Phase.FOUNDATIONAL_BUILD:
            require_phase1_disposition(session)
        if target in (Phase.FIT_CHECK, Phase.TAILORING):
            require_registry_populated(session)
        if target == Phase.TAILORING:
            require_fit_check_completed(session)
    except GateBlocked as exc:
        return ToolResult(
            passed=False,
            findings=[
                {
                    "severity": "Critical",
                    "issue": f"[{exc.gate_id}] {exc.message}",
                    "fix": (
                        f"The session is still in {previous.name}. Complete the "
                        "outstanding work, then advance again."
                    ),
                }
            ],
            data={"blocked_by_gate": exc.gate_id, "phase": previous.name},
        )

    session.phase = target
    return ToolResult(
        passed=True,
        data={"phase": target.name, "previous_phase": previous.name},
    )
