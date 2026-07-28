"""
Session state.

This is an in-memory implementation, and that is a KNOWN, ACCEPTED
limitation for the V1 deploy rather than an oversight: state is lost
on restart (including every Render deploy) and does not survive across
multiple instances, which is why the deploy is pinned to a single
always-on instance. V2's account-based storage replaces SessionStore's
dict with a real per-user store without changing its interface.

Because the process is now long-lived by design, sessions must expire
on their own; nothing else will ever reclaim them. See SessionStore's
eviction handling (B5, pre-deploy review 2026-07-25).

The isolation boundary (spec 7.6, T-9.12) is enforced here: every
lookup is keyed by (user_id, session_id) together, and a lookup with
the wrong user_id for a real session_id raises exactly the same error
as a session_id that doesn't exist at all. A caller cannot distinguish
"wrong session" from "wrong user for someone else's session," which is
the point: nothing here can be probed to confirm another user's
session_id is valid.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from typing import Dict, List, Optional, Tuple

from app.config import (
    MAX_ATTACHMENT_BYTES_PER_SESSION,
    MAX_ATTACHMENTS_PER_SESSION,
    MAX_SESSIONS_PER_USER,
    MAX_TRANSCRIPT_CHARS,
    MAX_TRANSCRIPT_MESSAGES,
    SESSION_TTL_SECONDS,
)
from app.usage import SessionUsage


def _carries_tool_result(message: Dict) -> bool:
    """Whether a stored message contains any tool_result block.

    Content is a plain string for ordinary user turns and a list of
    blocks for tool turns, so this has to handle both shapes rather than
    assuming either."""
    content = message.get("content")
    if not isinstance(content, list):
        return False
    return any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content)


class Phase(IntEnum):
    STARTING_POINT = 0
    AUDIT = 1
    FOUNDATIONAL_BUILD = 2
    SLOP_AUDIT = 3
    FORMATTING = 4
    FIT_CHECK = 5
    TAILORING = 6
    COVER_LETTER = 7
    FINAL_REVIEW = 8


@dataclass
class Fact:
    """Locked Facts Registry entry (spec section 5, tool list section 16)."""

    id: str
    type: str  # metric | date_span | entity | claim | skill | phrasing_lock
    value: str  # write-once; see supersede(), never mutate directly
    statement: str
    variants: List[str] = field(default_factory=list)
    source: Optional[str] = None
    role_ref: Optional[str] = None
    status: str = "active"  # active | superseded
    supersedes: Optional[str] = None
    co_occurs_with: List[str] = field(default_factory=list)

    def approve_variant(self, phrasing: str) -> None:
        """5.4: new variants require user approval before the value-match
        tool will accept them. Call this only from a path the user
        actually confirmed; there is no automatic path to this method."""
        if phrasing not in self.variants:
            self.variants.append(phrasing)


class CriticalNotDismissibleError(Exception):
    """Raised on any attempt to dismiss a Critical finding. Spec: the
    Iris Profile carries dismissed findings, with Critical findings
    excluded from dismissal."""


@dataclass
class Finding:
    id: str
    tool_id: str  # which T- item raised this
    severity: str  # Critical | High | Medium | Low
    issue: str
    fix: str
    content_signature: Optional[str] = None
    section: Optional[str] = None  # T-2.13: which careerInventory section this pertains to, if any
    dispositioned: bool = False  # T-1.8: fixed or acknowledged-with-reason
    disposition_reason: Optional[str] = None
    dismissed: bool = False  # advisory-tier only; see dismiss(), Critical is never dismissible

    def dismiss(self) -> None:
        """The ONLY supported way to set dismissed=True.

        Before 2026-07-25 this invariant existed solely as a comment on
        the field above, and apply_dismissed_findings (T-2.18) set the
        flag directly with no severity check. Because open_criticals()
        filters on `not dismissed`, and require_no_open_criticals
        (T-8.18) reads open_criticals(), dismissing a Critical opened
        the delivery gate: a model-callable tool could clear the exact
        finding the gate exists to hold. Reachable by prompt injection,
        by a malicious profile import, or by the model simply taking a
        shortcut under pressure to finish.

        Enforcing it on the model rather than at call sites is
        deliberate: a check in one caller is a check the next caller
        forgets."""
        if self.severity == "Critical":
            raise CriticalNotDismissibleError(
                f"Finding {self.id} ({self.tool_id}) is Critical and cannot be "
                "dismissed. Criticals are resolved by fixing the underlying "
                "issue or dispositioning them with a stated reason, never by "
                "dismissal."
            )
        self.dismissed = True


@dataclass
class LimitOverride:
    """T-8.21: records a per-instance authorization to exceed a default
    limit (bullet word count, cover letter length). Distinct from a
    config change: this covers exactly one artifact, not every future
    one."""

    limit_id: str  # e.g. "T-8.7" or "T-7.13"
    artifact_ref: str
    rationale: str
    recorded_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class Attachment:
    """An uploaded file, stored server-side. The model references this
    by id when calling ingest_document (T-0.1); it never receives the
    raw bytes as a tool argument, since typing tens of thousands of
    characters into a tool call just to name a file is exactly the
    token waste T-0.1's own docstring warns against.

    `data` holds raw bytes, not base64. It was base64 until 2026-07-27,
    which inflated every stored file by a third for no benefit: the one
    consumer that genuinely needs base64 (the docx_base64 tool argument
    the model-facing check schemas declare) encodes at that boundary
    instead, and that string is transient rather than retained for the
    life of the session."""

    id: str
    filename: str
    file_type: str  # "docx" or "pdf"
    data: bytes
    uploaded_at: float = field(default_factory=time.monotonic)
    extracted_text: Optional[str] = None  # T-0.1: cached raw text, set once ingest_document succeeds

    def byte_size(self) -> int:
        """Bytes this attachment holds in memory, including its cached
        extracted text. Both are real retained memory, so a budget that
        counted only the file would undercount a large text-heavy PDF
        by the size of everything extracted out of it."""
        return len(self.data) + (len(self.extracted_text.encode("utf-8")) if self.extracted_text else 0)


@dataclass
class RenderedFile:
    """A file produced by a rendering tool (resume docx, cover letter
    docx, Iris Profile markdown), stored server-side so the browser
    can download it via GET /sessions/{id}/files/{file_id}.

    The model never sends the raw bytes to the user — it stores them
    here and the SSE stream carries a 'file_ready' event with the
    file_id, which the frontend turns into a real download button."""

    id: str
    filename: str
    content_type: str  # "application/vnd.openxmlformats-officedocument.wordprocessingml.document" or "text/markdown"
    data_base64: str   # base64-encoded file bytes
    created_at: float = field(default_factory=time.monotonic)


@dataclass
class Session:
    session_id: str
    user_id: str
    phase: Phase = Phase.STARTING_POINT
    registry: Dict[str, Fact] = field(default_factory=dict)
    findings: List[Finding] = field(default_factory=list)
    limit_overrides: List[LimitOverride] = field(default_factory=list)
    foundational_fingerprint: Optional[str] = None  # T-2.19
    fit_check_gaps: List[str] = field(default_factory=list)  # T-6.15: carried into the cover letter
    fit_check_completed: bool = False  # T-5.1: must be true before Tailoring
    jd_text: Optional[str] = None  # T-6.1: current pasted job description
    jd_fingerprint: Optional[str] = None  # T-6.1: sha256 of jd_text, set on ingest
    gap_acknowledgments: Dict[str, str] = field(default_factory=dict)  # T-7.8: gap text -> stated reason
    fix_attempts: Dict[str, int] = field(default_factory=dict)  # T-8.19: keyed by content signature
    active_batch_id: Optional[str] = None  # T-9.7: None means no batch currently open
    pending_amendment_reason: Optional[str] = None  # T-9.6: set when a decision changes a rule, cleared once the diff is committed
    locked_package_versions: Dict[str, int] = field(default_factory=dict)  # T-9.8: artifact_ref -> version
    messages: List[Dict] = field(default_factory=list)  # B1: server-owned transcript, never client-supplied
    created_at: float = field(default_factory=time.monotonic)
    last_accessed: float = field(default_factory=time.monotonic)  # B5: drives idle eviction
    attachments: Dict[str, Attachment] = field(default_factory=dict)  # T-0.1: uploaded files, keyed by attachment id
    rendered_files: Dict[str, RenderedFile] = field(default_factory=dict)  # output files ready for browser download
    usage: SessionUsage = field(default_factory=SessionUsage)  # running token/cost totals; see app/usage.py

    def add_rendered_file(self, filename: str, content_type: str, data_base64: str) -> RenderedFile:
        rendered = RenderedFile(
            id=str(uuid.uuid4()),
            filename=filename,
            content_type=content_type,
            data_base64=data_base64,
        )
        self.rendered_files[rendered.id] = rendered
        return rendered

    def get_rendered_file(self, file_id: str) -> Optional[RenderedFile]:
        return self.rendered_files.get(file_id)

    def attachment_bytes(self) -> int:
        """Total memory currently held by this session's attachments."""
        return sum(a.byte_size() for a in self.attachments.values())

    def _evict_oldest_attachment(self) -> None:
        oldest_id = min(self.attachments, key=lambda k: self.attachments[k].uploaded_at)
        del self.attachments[oldest_id]

    def add_attachment(self, filename: str, file_type: str, data: bytes) -> Attachment:
        """Stores an uploaded file and returns a reference the model
        can cite by id in a tool call.

        Two independent ceilings, both evicting oldest-first, the same
        policy SessionStore already applies to its own per-user session
        quota. The count cap alone was not enough: ten files just under
        the per-file limit satisfied it while still holding far more
        memory than the instance can spare, which is the hole the byte
        budget closes (2026-07-27)."""
        if len(self.attachments) >= MAX_ATTACHMENTS_PER_SESSION:
            self._evict_oldest_attachment()

        incoming = len(data)
        # Evict until the newcomer fits. Guarded on a non-empty dict so a
        # single file larger than the whole budget cannot spin here; the
        # upload route rejects that case up front (MAX_UPLOAD_BYTES is
        # well under the session budget), and if it ever changed, storing
        # one oversized file beats looping forever.
        while self.attachments and self.attachment_bytes() + incoming > MAX_ATTACHMENT_BYTES_PER_SESSION:
            self._evict_oldest_attachment()

        attachment = Attachment(
            id=str(uuid.uuid4()),
            filename=filename,
            file_type=file_type,
            data=data,
        )
        self.attachments[attachment.id] = attachment
        return attachment

    def get_attachment(self, attachment_id: str) -> Optional[Attachment]:
        return self.attachments.get(attachment_id)

    def append_messages(self, new_messages: List[Dict]) -> None:
        """Appends to the server-owned transcript, trimming oldest
        first.

        The transcript lives here, not in the request body, because a
        client-supplied history is a client-authored history: it lets a
        caller forge assistant turns and tool_result blocks claiming
        checks already passed, which is precisely the model
        self-report that spec rule 4.1 refuses to accept as
        enforcement (B1, pre-deploy review 2026-07-25)."""
        self.messages.extend(new_messages)
        self.trim_transcript()

    def trim_transcript(self) -> None:
        """Applies both transcript ceilings, oldest dropped first.

        The count cap alone bounds how many turns are retained but says
        nothing about their size, and a transcript's cost is driven by
        characters, not turns: one tool result carrying an extracted
        document can outweigh ninety-nine ordinary messages. The
        character backstop is what makes worst-case context bounded
        rather than merely typical-case reasonable (2026-07-27).

        Kept as a method rather than inlined at the two call sites so
        the /chat route's wholesale transcript replacement and the
        incremental append path cannot drift apart on which caps they
        apply."""
        if len(self.messages) > MAX_TRANSCRIPT_MESSAGES:
            self.messages = self.messages[-MAX_TRANSCRIPT_MESSAGES:]

        # Always keep at least the newest message, even if it alone
        # exceeds the budget: dropping the turn the model is mid-way
        # through is worse than briefly exceeding a soft ceiling, and
        # the real ceilings (MAX_INGEST_TEXT_CHARS, INLINE_EXTRACT_CHARS)
        # already bound how large any single message can get.
        while len(self.messages) > 1 and self.transcript_chars() > MAX_TRANSCRIPT_CHARS:
            self.messages.pop(0)

        self._drop_orphaned_tool_results()

    def _drop_orphaned_tool_results(self) -> None:
        """Ensures the transcript never begins with a tool_result whose
        tool_use was trimmed away.

        The Anthropic API rejects that shape outright: every tool_result
        must be preceded by the assistant tool_use it answers. Trimming
        by character budget alone is blind to that pairing, so popping
        an assistant message carrying a tool_use while keeping the user
        message carrying its tool_result produced a transcript the API
        refused with a 400.

        The failure was worse than a single rejected request. The
        orphaned block stayed at the head of the stored transcript, so
        every later turn in that session rebuilt the same invalid
        request and got the same 400 - unrecoverable without starting
        over. Confirmed live 2026-07-28 (a 338-page performance export;
        see MAX_FINDINGS_PER_CHECK in config.py for the oversized tool
        result that triggered the trim in the first place).

        Deliberately not guarded by "keep at least one message" the way
        the character trim above is. A tool_result at the head is
        orphaned by definition, since a valid one is always preceded by
        its tool_use, so dropping it is right however few remain.
        Emptying the transcript is a clean state: the next turn opens
        with the user's new message, which is exactly a fresh
        conversation. Keeping one invalid message instead would preserve
        the 400 forever, which is the bug."""
        while self.messages and _carries_tool_result(self.messages[0]):
            self.messages.pop(0)

    def transcript_chars(self) -> int:
        return sum(len(str(m.get("content", ""))) for m in self.messages)

    def active_facts(self) -> List[Fact]:
        return [f for f in self.registry.values() if f.status == "active"]

    def is_registry_empty(self) -> bool:
        return len(self.active_facts()) == 0

    def open_criticals(self) -> List[Finding]:
        """Defense in depth: Finding.dismiss() already refuses to set
        the flag on a Critical, so the `not f.dismissed` clause should
        be unreachable for Criticals. It stays anyway, because a
        Finding constructed directly with dismissed=True (a profile
        import, a future code path, a test fixture) would otherwise
        slip past the gate. Two independent things now have to fail
        before a Critical goes quiet."""
        return [
            f
            for f in self.findings
            if f.severity == "Critical" and not f.dismissed
        ]

    def undispositioned_phase1_criticals(self) -> List[Finding]:
        return [
            f
            for f in self.open_criticals()
            if f.tool_id.startswith("T-1.") and not f.dispositioned
        ]


class SessionNotFoundError(KeyError):
    """Raised for a missing session AND for a real session_id under the
    wrong user_id. Deliberately the same exception in both cases."""


class SessionStore:
    """Keyed by (user_id, session_id) as a TUPLE, not a joined string.

    T-9.13 (concurrency): a lock guards every mutation of the
    `_sessions` dict, since FastAPI runs sync route handlers in a
    thread pool. Note carefully what that does and does not cover.
    The lock protects the MAPPING. It does not protect the Session
    objects inside it: get() returns a live reference, and callers
    mutate that object after the lock is released. Per-session locks
    (see lock_for) are provided for callers that need to serialize
    work on one session. The earlier version of this docstring claimed
    a broader guarantee than the code provided (S1, pre-deploy review
    2026-07-25); this states the real boundary.

    T-9.12 (isolation): a wrong-user lookup and a nonexistent-session
    lookup raise the identical error, so the store cannot be probed to
    confirm someone else's session_id exists.

    B5: sessions expire. Nothing else reclaims them in a process that
    is deliberately never restarted.
    """

    def __init__(self) -> None:
        self._sessions: Dict[Tuple[str, str], Session] = {}
        self._session_locks: Dict[Tuple[str, str], threading.Lock] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _key(user_id: str, session_id: str) -> Tuple[str, str]:
        """A tuple, deliberately.

        The previous implementation joined these with a colon.
        session_id arrives straight off the URL path and is fully
        caller-controlled, so a user_id containing the delimiter would
        have made two different (user, session) pairs collide on one
        key. Clerk's opaque `user_...` subjects contain no colons, so
        this was never live, but a tuple makes the whole class of
        delimiter-confusion bug structurally impossible instead of
        contingent on an identity provider's formatting (S2,
        pre-deploy review 2026-07-25)."""
        return (user_id, session_id)

    def _evict_expired_locked(self, now: float) -> None:
        """Caller must hold self._lock."""
        expired = [k for k, s in self._sessions.items() if now - s.last_accessed > SESSION_TTL_SECONDS]
        for key in expired:
            del self._sessions[key]
            self._session_locks.pop(key, None)

    def _enforce_user_quota_locked(self, user_id: str) -> None:
        """Caller must hold self._lock. Drops that user's least
        recently used sessions past the cap, so one user cannot exhaust
        a shared instance's memory by opening sessions in a loop."""
        owned = sorted(
            (k for k in self._sessions if k[0] == user_id),
            key=lambda k: self._sessions[k].last_accessed,
        )
        while len(owned) >= MAX_SESSIONS_PER_USER:
            key = owned.pop(0)
            del self._sessions[key]
            self._session_locks.pop(key, None)

    def create(self, user_id: str) -> Session:
        now = time.monotonic()
        with self._lock:
            self._evict_expired_locked(now)
            self._enforce_user_quota_locked(user_id)
            session_id = str(uuid.uuid4())
            session = Session(session_id=session_id, user_id=user_id)
            self._sessions[self._key(user_id, session_id)] = session
            return session

    def get(self, user_id: str, session_id: str) -> Session:
        key = self._key(user_id, session_id)
        now = time.monotonic()
        with self._lock:
            self._evict_expired_locked(now)
            if key not in self._sessions:
                raise SessionNotFoundError(session_id)
            session = self._sessions[key]
            session.last_accessed = now
            return session

    def lock_for(self, user_id: str, session_id: str) -> threading.Lock:
        """A per-session lock, for callers that need to serialize
        mutation of one session across concurrent requests. Created on
        demand and reused, so two callers asking for the same
        session's lock get the same object."""
        key = self._key(user_id, session_id)
        with self._lock:
            if key not in self._session_locks:
                self._session_locks[key] = threading.Lock()
            return self._session_locks[key]

    def save(self, session: Session) -> None:
        """Sessions are stored by reference, so mutations are already
        visible without this; it exists so callers read naturally and
        so a future store that genuinely needs a write step can be
        dropped in behind the same interface."""
        with self._lock:
            session.last_accessed = time.monotonic()
            self._sessions[self._key(session.user_id, session.session_id)] = session

    def delete(self, user_id: str, session_id: str) -> None:
        """T-9.11: session-scoped data store. Registry, term lists, and
        preferences are discarded at logout, with no persistence beyond
        this process. Raises the same SessionNotFoundError as get() for
        a missing or wrong-user session_id, so this call cannot be used
        to probe whether another user's session exists either."""
        key = self._key(user_id, session_id)
        with self._lock:
            if key not in self._sessions:
                raise SessionNotFoundError(session_id)
            del self._sessions[key]
            self._session_locks.pop(key, None)

    def count(self) -> int:
        with self._lock:
            return len(self._sessions)


store = SessionStore()
