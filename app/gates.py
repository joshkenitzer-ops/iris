"""
Gate engine.

Spec rule 4.1: a model asserting compliance without an underlying
deterministic scan is never sufficient to clear a Critical or Pedantic
finding. That rule has a consequence for architecture, not just for
prompting: a GATE cannot be implemented only as a tool schema the
model is free to call or skip. If invoking the check is optional, a
model under pressure to finish can skip it, and the gate stops
existing.

So every GATE in docs/iris-tool-list.md gets a method here, and the
FastAPI route handling the relevant phase transition calls that method
directly, in Python, before allowing the transition. The same
underlying logic may ALSO be exposed to Claude as a tool schema (see
the tool registry in app/tools/) so the model can self-check and
explain its reasoning, but the exposed tool is never the only thing standing
between a broken package and delivery. Both paths call the same
function; only one of them is optional.

Spec rule 4.4: gates in Phases 0-7 interrupt at the point they fire.
Phase 8 is the named exception, an end-of-run batch by design. That
distinction is why require_no_open_criticals is meant to be called
once, at the Phase 8 boundary, rather than after every finding.
"""

from __future__ import annotations

import re

from app.session import Session


class GateBlocked(Exception):
    def __init__(self, gate_id: str, message: str):
        self.gate_id = gate_id
        self.message = message
        super().__init__(f"[{gate_id}] {message}")


def require_registry_populated(session: Session) -> None:
    """T-5.2 / spec 5.9: empty registry blocks Fit Check and Tailoring."""
    if session.is_registry_empty():
        raise GateBlocked(
            "T-5.2",
            "Locked Facts Registry is empty. Complete Master Resume Build "
            "before Fit Check or Tailoring.",
        )


def require_phase1_disposition(session: Session) -> None:
    """T-1.8: Phase 2 cannot begin while a Phase 1 Critical is
    undispositioned. Fixed or acknowledged-with-reason both satisfy it."""
    undispositioned = session.undispositioned_phase1_criticals()
    if undispositioned:
        raise GateBlocked(
            "T-1.8",
            f"{len(undispositioned)} Phase 1 Critical finding(s) require "
            "disposition (fixed, or acknowledged with a stated reason) "
            "before Phase 2 can begin.",
        )


def require_no_open_criticals(session: Session) -> None:
    """T-8.18: no Critical finding may be open at delivery. Call once, at
    the Phase 8 -> delivery boundary, per spec rule 4.4."""
    open_criticals = session.open_criticals()
    if open_criticals:
        raise GateBlocked(
            "T-8.18",
            f"{len(open_criticals)} open Critical finding(s) must be "
            "resolved before either document is delivered.",
        )


def require_fit_check_completed(session: Session) -> None:
    """T-5.1: Fit Check must run before any tailoring, on every
    submission. session.fit_check_completed is reset to False whenever
    a new JD is submitted (the caller's responsibility, not this
    function's), so this cannot be satisfied by a stale prior run."""
    if not session.fit_check_completed:
        raise GateBlocked(
            "T-5.1",
            "Fit Check has not run for this submission. It must run "
            "before Tailoring, every time, no exceptions.",
        )


_COMP_RANGE_RE = re.compile(r"\$[\d,]+\s*(?:-|to)\s*\$?[\d,]+")


def require_no_fabricated_compensation_range(search_succeeded: bool, presented_text: str) -> None:
    """T-5.8: if the market compensation search failed or returned no
    reliable result, the presented text must say so plainly rather
    than contain a fabricated numeric range."""
    if search_succeeded:
        return
    if _COMP_RANGE_RE.search(presented_text):
        raise GateBlocked(
            "T-5.8",
            "Compensation search did not return a reliable result, "
            "but the presented text contains a numeric range anyway.",
        )


def require_turn_completion(session: Session) -> None:
    """T-9.6: if a decision this turn changed a rule and no amendment
    diff was produced, the turn is incomplete. app/tools/harness_meta.py
    provides flag_pending_amendment and clear_pending_amendment as the
    two state transitions; this gate is what the harness checks at the
    end of a turn, independent of whether the model remembered to."""
    if session.pending_amendment_reason is not None:
        raise GateBlocked(
            "T-9.6",
            f"A decision changed a rule this turn ('{session.pending_amendment_reason}') "
            "but no amendment diff was committed. Narrating a change without "
            "writing it is an incomplete turn.",
        )


def require_no_unresolved_markers(text: str) -> None:
    """T-6.14: no document ships with an unresolved [ADD METRIC: ...]
    marker. Delegates to app.tools.delivery.check_unresolved_markers,
    the same function exposed to Claude as a tool, so there is one
    implementation of this rule rather than two that could drift."""
    from app.tools.delivery import check_unresolved_markers

    result = check_unresolved_markers(text)
    if not result.passed:
        raise GateBlocked("T-6.14", result.findings[0]["issue"])


def require_gap_not_silently_removed(session: Session, final_text: str) -> None:
    """T-7.8: a Fit Check gap may be softened in the final text, but its
    disappearance must carry a recorded acknowledgment
    (app.tools.tailoring.record_gap_acknowledgment). v0.4 left this an
    Open Question leaning toward required acknowledgment; making it a
    gate means silent removal of a flagged finding is structurally
    impossible rather than merely discouraged. A gap that still
    appears in the final text, verbatim, needs no acknowledgment at
    all, since nothing was removed."""
    final_lower = final_text.lower()
    for gap in session.fit_check_gaps:
        gap_lower = gap.strip().lower()
        if not gap_lower:
            continue
        if gap_lower not in final_lower and gap not in session.gap_acknowledgments:
            raise GateBlocked(
                "T-7.8",
                f"Fit Check gap '{gap}' no longer appears in the final text "
                "and has no recorded acknowledgment. Acknowledge its removal "
                "with a stated reason, or restate the gap honestly.",
            )


def require_amendment_confirmed(confirmed: bool) -> None:
    """T-9.5: never auto-commits a spec amendment. A diff can be
    generated freely (T-9.4, generate_amendment_diff), but writing it
    to docs/iris-spec.md requires this to have been called with
    confirmed=True, sourced from an explicit user confirmation rather
    than a model's assumption that silence means agreement. Distinct
    from T-9.6 (require_turn_completion): that gate catches a turn
    that changed a rule and produced no diff at all; this one gates
    the separate step of actually committing a diff that was
    produced."""
    if not confirmed:
        raise GateBlocked(
            "T-9.5",
            "Amendment diff was produced but not explicitly confirmed. "
            "Propose, show the diff, and wait; never commit on inference.",
        )


def check_profile_fingerprint(session: Session, uploaded_master_fingerprint: str) -> bool:
    """T-2.19: warn and proceed, never block. Returns True on match; the
    caller decides what "warn" means for its surface (a banner, a log
    line), but this function never raises."""
    if session.master_fingerprint is None:
        session.master_fingerprint = uploaded_master_fingerprint
        return True
    return session.master_fingerprint == uploaded_master_fingerprint
