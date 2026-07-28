"""Per-turn token accounting.

Iris spends real money on every /chat turn, and until now the only
record of how much was a log line reporting `~%d chars of transcript`:
an estimate of the input side, derived from string lengths, with no
output side and no cost at all. The Anthropic SDK has been returning
the real figures the whole time on the Message object that ends every
call. This module accumulates them.

The unit is the TURN, not the API call. One user action ("run the
audit") is one stream_turn call that loops through several API calls as
the model works through its tools. The question this exists to answer,
"what does an audit cost," is about the whole loop, so usage
accumulates across it and is reported once at the end.

Four token classes, not one
---------------------------
The API reports four counts and they bill at four different rates. This
is the entire reason for a dedicated module rather than a running
integer:

    input_tokens                  1.00x   uncached input
    cache_creation_input_tokens   1.25x   written to cache this call
    cache_read_input_tokens       0.10x   served from cache
    output_tokens                 1.00x   at the output rate

Iris pins the spec and all 97 tool schemas with cache_control on every
call, so on a typical turn most input tokens are cache reads at a tenth
of the input rate. Collapsing these into one number would overstate
input cost by close to an order of magnitude on the cached portion.

Attribution
-----------
Labeling uses the tool-list numbering rather than a keyword heuristic
on the user's message. Every registered tool carries an id like
"T-3.1", and that major number is already the pipeline phase (see
Phase in session.py, which uses the same numbering): T-1 is Audit, T-2
Foundational Build, T-7 Cover Letter, and so on. T-9 is harness
plumbing and belongs to no phase.

That matters because session.phase is not usable for this. The
2026-07-27 review established that sessions never actually leave
STARTING_POINT, so a phase-keyed measurement would file every turn
under one bucket. The tools that ran are ground truth about what the
turn did; the phase field is not.

The derived label is a convenience, and a lossy one: a turn is tagged
with its modal phase, ties broken toward the earlier phase on the
reasoning that later-phase tools appearing in an earlier-phase turn are
usually verification of the work the turn is doing, not the work
itself. A Foundational Build that ends by running formatting checks is
a build, not a formatting pass. The full per-phase call counts and the
raw tool-id list are recorded alongside it, so disagreeing with that
rule later is a question you can ask of the existing logs rather than a
reason to re-instrument.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.config import (
    CACHE_READ_MULTIPLIER,
    CACHE_WRITE_MULTIPLIER,
    PRICE_INPUT_PER_MTOK,
    PRICE_OUTPUT_PER_MTOK,
)

# Major number -> label, matching Phase in session.py exactly. Kept as a
# literal map rather than derived from Phase because the tool list is
# the thing being read here, and it is allowed to carry majors (9) that
# are not phases at all.
PHASE_LABELS: Dict[int, str] = {
    0: "intake",
    1: "audit",
    2: "foundational_build",
    3: "slop_audit",
    4: "formatting",
    5: "fit_check",
    6: "tailoring",
    7: "cover_letter",
    8: "final_review",
}

# T-9.x is harness plumbing (spec load, batch bookkeeping, amendment
# tracking). It runs during turns of every kind and describes none of
# them, so it is excluded from labeling rather than allowed to win a
# modal vote.
HARNESS_MAJOR = 9

# A turn that called no tools at all: conversation, guidance, a question
# answered from context. Real and worth measuring separately, since it
# is the cheapest interaction type and there are a lot of them.
NO_TOOLS_LABEL = "conversation"

# Tools ran, but none that map to a phase (only T-9, or ids in a shape
# this cannot parse). Deliberately distinct from "conversation": one
# means no tools, the other means the labeler could not read them, and
# collapsing the two would hide a labeling bug as a usage pattern.
UNLABELED = "unclassified"

_TOOL_ID_RE = re.compile(r"^T-(\d+)\.")


def phase_major(tool_id: str) -> Optional[int]:
    """Major number from a tool id: "T-3.1" -> 3.

    Returns None for anything that does not parse, rather than raising.
    An unrecognized id shape is a labeling miss, not a reason to fail a
    turn that has already done its work and spent its money."""
    match = _TOOL_ID_RE.match(tool_id.strip())
    return int(match.group(1)) if match else None


@dataclass
class TurnUsage:
    """Token and cost totals for one user turn.

    Mutable and accumulated in place across the tool loop's API calls.
    Every counter defaults to zero, so a turn that fails before its
    first call still produces a valid (empty) record rather than None,
    and the caller never has to branch on whether measurement happened.
    """

    input_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    output_tokens: int = 0
    api_calls: int = 0
    tool_ids: List[str] = field(default_factory=list)
    tool_names: List[str] = field(default_factory=list)

    def record_call(self, usage: Any) -> None:
        """Fold one API response's usage into the turn.

        Takes the SDK's usage object directly. Every field is read
        defensively: the two cache counters are absent or None on some
        responses, and this must never be the thing that breaks a turn.
        Measurement code has no business raising inside a path that is
        otherwise succeeding.

        A missing usage object still counts as an API call. The call was
        made and billed whether or not its numbers came back, and
        dropping it would understate calls-per-turn while leaving the
        token totals equally short."""
        self.api_calls += 1
        if usage is None:
            return
        self.input_tokens += int(getattr(usage, "input_tokens", 0) or 0)
        self.output_tokens += int(getattr(usage, "output_tokens", 0) or 0)
        self.cache_creation_tokens += int(
            getattr(usage, "cache_creation_input_tokens", 0) or 0
        )
        self.cache_read_tokens += int(
            getattr(usage, "cache_read_input_tokens", 0) or 0
        )

    def record_tool(self, name: str, tool_id: Optional[str]) -> None:
        """Note that a tool ran. `tool_id` is optional because a name
        the registry cannot resolve still tells us a tool was called."""
        self.tool_names.append(name)
        if tool_id:
            self.tool_ids.append(tool_id)

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.cache_creation_tokens
            + self.cache_read_tokens
            + self.output_tokens
        )

    @property
    def cost_usd(self) -> float:
        """Estimated cost at the rates in config.py.

        An estimate, deliberately: config holds a local copy of a price
        Anthropic owns. Good for comparing interaction types against
        each other, which is what it is for. The Console is the record
        of what was actually billed."""
        input_side = (
            self.input_tokens
            + self.cache_creation_tokens * CACHE_WRITE_MULTIPLIER
            + self.cache_read_tokens * CACHE_READ_MULTIPLIER
        ) * PRICE_INPUT_PER_MTOK
        output_side = self.output_tokens * PRICE_OUTPUT_PER_MTOK
        return (input_side + output_side) / 1_000_000

    def phase_counts(self) -> Dict[str, int]:
        """Tool calls per phase label, harness tools excluded."""
        counts: Counter = Counter()
        for tool_id in self.tool_ids:
            major = phase_major(tool_id)
            if major is None or major == HARNESS_MAJOR:
                continue
            counts[PHASE_LABELS.get(major, UNLABELED)] += 1
        return dict(counts)

    def label(self) -> str:
        """Best single name for what this turn was doing.

        Modal phase, ties broken toward the earlier phase. See the
        module docstring for why that tie-break, and why this is a
        convenience over the raw counts rather than the measurement
        itself."""
        if not self.tool_names:
            return NO_TOOLS_LABEL
        counts = self.phase_counts()
        if not counts:
            return UNLABELED
        # Sort by count descending, then by phase order ascending. The
        # second key is the tie-break, and it needs the major number
        # rather than the label, since alphabetical order over labels is
        # not pipeline order.
        by_label_major = {
            label: major for major, label in PHASE_LABELS.items()
        }
        return min(
            counts.items(),
            key=lambda item: (-item[1], by_label_major.get(item[0], 99)),
        )[0]

    def as_log_fields(self) -> Dict[str, Any]:
        """Flat dict for the structured log line. Token classes stay
        separate here on purpose: a reader recomputing cost at a
        different price, or for a different model, needs the four
        counts, not the total and not the dollar figure."""
        return {
            "label": self.label(),
            "calls": self.api_calls,
            "in": self.input_tokens,
            "cache_w": self.cache_creation_tokens,
            "cache_r": self.cache_read_tokens,
            "out": self.output_tokens,
            "total": self.total_tokens,
            "cost_usd": round(self.cost_usd, 4),
        }


@dataclass
class SessionUsage:
    """Running totals for one session.

    Lives on Session, so it dies with the in-memory session store on
    deploy. That is the same accepted V1 limitation as everything else
    held there (see R-4 in the production readiness review); the log
    line written per turn is the durable record, and this is what makes
    a cumulative "this session has cost X" view possible without one.
    """

    turns: int = 0
    input_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    output_tokens: int = 0
    api_calls: int = 0
    by_label: Dict[str, int] = field(default_factory=dict)

    def record_turn(self, turn: TurnUsage) -> None:
        """Fold a completed turn into the session totals.

        A turn that made no API calls is not counted. Those exist: a
        turn can fail on a missing API key or a client disconnect before
        anything is sent, and counting it would inflate the denominator
        of every per-turn average computed from this."""
        if turn.api_calls == 0:
            return
        self.turns += 1
        self.api_calls += turn.api_calls
        self.input_tokens += turn.input_tokens
        self.cache_creation_tokens += turn.cache_creation_tokens
        self.cache_read_tokens += turn.cache_read_tokens
        self.output_tokens += turn.output_tokens
        label = turn.label()
        self.by_label[label] = self.by_label.get(label, 0) + 1

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.cache_creation_tokens
            + self.cache_read_tokens
            + self.output_tokens
        )

    @property
    def cost_usd(self) -> float:
        """Same rate math as TurnUsage.cost_usd, over session totals.

        Computed from the accumulated counts rather than by summing
        per-turn costs, so rounding never compounds across a long
        session."""
        input_side = (
            self.input_tokens
            + self.cache_creation_tokens * CACHE_WRITE_MULTIPLIER
            + self.cache_read_tokens * CACHE_READ_MULTIPLIER
        ) * PRICE_INPUT_PER_MTOK
        output_side = self.output_tokens * PRICE_OUTPUT_PER_MTOK
        return (input_side + output_side) / 1_000_000
