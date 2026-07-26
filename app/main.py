"""
FastAPI entry point.

Run with: uvicorn app.main:app --reload
Requires: pip install -r requirements.txt, ANTHROPIC_API_KEY set,
CLERK_ISSUER set (see app/clerk_auth.py). Optional: CLERK_AUTHORIZED_PARTIES,
ALLOWED_ORIGINS (comma-separated; unset means no browser origin is
allowed, not a wildcard).

T-9.10 (authentication): get_current_user_id() verifies a real Clerk
session token (app.clerk_auth) rather than trusting a client-supplied
header. Nothing client-supplied is ever treated as identity; the
verified `sub` claim from a signature-checked, non-expired,
correct-issuer JWT is the only source of user_id anywhere in this
file. Everything downstream, session isolation (T-9.12), the profile
file, already receives a verified user_id from this function; that
was true even in the old header-stub version, which is why swapping
the implementation was a one-function change, not a redesign.

Also hardened here per the same pass: CORS is locked to explicit
origins (empty by default, never "*"), and unhandled exceptions return
a generic 500 with no exception content, so nothing internal (a stack
trace, an accidental secret in an error message) reaches a client.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import app.tools  # noqa: F401  (import for its decorator side effects; do not remove)
from app.claude_client import stream_turn
from app.clerk_auth import ClerkAuthError, get_verifier
from app.config import (
    CHAT_RATE_LIMIT_CALLS,
    CHAT_RATE_LIMIT_WINDOW_SECONDS,
    MAX_MESSAGE_CHARS,
    MAX_TRANSCRIPT_MESSAGES,
    MAX_UPLOAD_BYTES,
)
from app.enforcement import registry
from app.gates import (
    GateBlocked,
    require_fit_check_completed,
    require_gap_not_silently_removed,
    require_no_open_criticals,
    require_phase1_disposition,
    require_registry_populated,
)
from app.session import Phase, Session, SessionNotFoundError, store
from app.spec_loader import load_spec_text

SPEC_PATH = Path(__file__).resolve().parent.parent / "docs" / "iris-spec.md"
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

# Without this, nothing this app logs ever reaches the host's log
# stream. A bare logging.getLogger() has no handler, and uvicorn
# configures only its own loggers, so every logger.exception() in this
# file, including the one in the unhandled-exception handler below,
# was being written into the void. That was discovered on 2026-07-26
# while trying to diagnose a production 500: the handler was doing
# exactly its job and the traceback still never appeared in Render's
# logs, which made the one tool built for diagnosing failures useless
# at the moment it was needed.
logging.basicConfig(
    level=os.environ.get("IRIS_LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

logger = logging.getLogger("iris")

# Docs endpoints are OFF unless explicitly enabled. FastAPI serves
# /docs, /redoc, and /openapi.json publicly by default, which on a
# public host hands any anonymous visitor a complete interactive map of
# every route, schema, and field, plus a precise target list. Set
# IRIS_ENABLE_DOCS=true locally when you want them (pre-deploy review
# 2026-07-25, item 3).
_DOCS_ENABLED = os.environ.get("IRIS_ENABLE_DOCS", "").lower() in {"1", "true", "yes"}

# N3: the spec is read once at startup, not re-read from disk on every
# chat request.
_spec_cache: Dict[str, str] = {}


def _get_spec_text() -> str:
    if "text" not in _spec_cache:
        _spec_cache["text"] = load_spec_text(SPEC_PATH)
    return _spec_cache["text"]


def _clerk_frontend_host() -> str:
    """The bare hostname Clerk's browser bundles are served from,
    derived from CLERK_ISSUER rather than configured separately.

    CLERK_ISSUER is kept verbatim for JWT verification (app.clerk_auth
    compares it against the token's `iss` claim, which includes the
    scheme, so it must NOT be mutated there). Script URLs need the
    host without a scheme, since the frontend builds
    "https://{host}/npm/...". Deriving one from the other means there
    is only ever one value to configure, and normalizing here makes
    the duplicated-scheme bug ("https://https//...") structurally
    impossible no matter how the env var is pasted in."""
    issuer = os.environ.get("CLERK_ISSUER", "").strip()
    for scheme in ("https://", "http://"):
        if issuer.startswith(scheme):
            issuer = issuer[len(scheme) :]
            break
    return issuer.rstrip("/")


_CLERK_HOST_TOKEN = "__CLERK_FRONTEND_HOST__"
_CLERK_KEY_TOKEN = "__CLERK_PUBLISHABLE_KEY__"

# The fully rendered index.html, built once at startup. Its inputs
# (env vars, a file on disk) cannot change while the process runs, so
# there is nothing to gain from re-rendering per request.
_index_cache: Dict[str, str] = {}


def _render_index() -> str:
    """Substitutes the Clerk template tokens in static/index.html with
    values from the environment.

    Templating rather than committing the values keeps
    environment-specific config in the environment, which is the whole
    point of the 2026-07-26 change: the values previously lived in the
    committed HTML, so shipping that file overwrote a live
    deployment's config and broke sign-in.

    Templating rather than injecting the scripts from JavaScript at
    runtime is the second half of that lesson. Runtime injection was
    tried first and failed: Clerk's bundle discovers its publishable
    key from its own script tag, and that discovery does not work
    reliably for dynamically-inserted scripts, leaving `Clerk`
    undefined. This keeps Clerk's documented static tags exactly as
    they ship them."""
    template = (STATIC_DIR / "index.html").read_text(encoding="utf-8")

    # A future edit that drops the tokens would otherwise silently
    # serve a page pointing at a literal "__CLERK_FRONTEND_HOST__"
    # hostname, which is precisely the failure this change exists to
    # prevent. Fail at boot instead.
    for token in (_CLERK_HOST_TOKEN, _CLERK_KEY_TOKEN):
        if token not in template:
            raise RuntimeError(
                f"static/index.html is missing the {token} template token. "
                "The Clerk script tags must keep their template tokens; set "
                "real values via environment variables, never in the file."
            )

    return template.replace(_CLERK_HOST_TOKEN, _clerk_frontend_host()).replace(
        _CLERK_KEY_TOKEN, os.environ.get("CLERK_PUBLISHABLE_KEY", "").strip()
    )


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    """N4: /chat reads the spec from disk, and / serves the frontend
    shell from disk. If either is missing from the deployed tree,
    fail loudly at boot rather than with a 500 on the first request.

    CLERK_PUBLISHABLE_KEY is checked here for the same reason: without
    it the frontend cannot render a sign-in form at all, and a browser
    console error is a far worse way to discover that than a refused
    boot with a message naming the exact missing variable."""
    if not SPEC_PATH.is_file():
        raise RuntimeError(
            f"Spec file not found at {SPEC_PATH}. docs/iris-spec.md must be "
            "committed and present in the deployed tree."
        )
    if not (STATIC_DIR / "index.html").is_file():
        raise RuntimeError(
            f"Frontend not found at {STATIC_DIR / 'index.html'}. The static/ "
            "directory must be committed and present in the deployed tree."
        )
    if not os.environ.get("CLERK_PUBLISHABLE_KEY", "").strip():
        raise RuntimeError(
            "CLERK_PUBLISHABLE_KEY is not set. The frontend needs it to render "
            "a sign-in form; without it every visitor gets a blank page. Set it "
            "from the Clerk dashboard's API Keys page (the value starting 'pk_')."
        )
    if not _clerk_frontend_host():
        raise RuntimeError(
            "CLERK_ISSUER is not set, so the Clerk frontend host cannot be "
            "derived. Set it to your Clerk Frontend API URL."
        )
    _get_spec_text()
    _index_cache["html"] = _render_index()
    yield


app = FastAPI(
    lifespan=_lifespan,
    title="Iris Harness",
    version="0.1.0",
    debug=False,
    docs_url="/docs" if _DOCS_ENABLED else None,
    redoc_url="/redoc" if _DOCS_ENABLED else None,
    openapi_url="/openapi.json" if _DOCS_ENABLED else None,
)


class _RateLimiter:
    """B4: a per-user rolling-window cap on the endpoint that spends
    money. In-memory and per-instance, which matches the single-instance
    deploy; a shared store is the V2 upgrade alongside session storage.

    This is not the usage-accounting feature that was deferred. It is a
    ceiling, so that one leaked token, a runaway client retry loop, or
    an accidental very large paste cannot run up an unbounded bill."""

    def __init__(self, max_calls: int, window_seconds: int) -> None:
        self._max = max_calls
        self._window = window_seconds
        self._hits: Dict[str, List[float]] = {}
        self._lock = threading.Lock()

    def check(self, user_id: str) -> None:
        now = time.monotonic()
        with self._lock:
            recent = [t for t in self._hits.get(user_id, []) if now - t < self._window]
            if len(recent) >= self._max:
                retry_after = int(self._window - (now - recent[0])) + 1
                raise HTTPException(
                    status_code=429,
                    detail="Rate limit exceeded. Try again shortly.",
                    headers={"Retry-After": str(retry_after)},
                )
            recent.append(now)
            self._hits[user_id] = recent


_chat_rate_limiter = _RateLimiter(CHAT_RATE_LIMIT_CALLS, CHAT_RATE_LIMIT_WINDOW_SECONDS)

_allowed_origins = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,  # empty = no browser origin is allowed until ALLOWED_ORIGINS is set
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def _no_internals_leak(request: Request, exc: Exception) -> JSONResponse:
    """Anything not already turned into an HTTPException lands here.
    Logged in full server-side for debugging; the client gets nothing
    beyond the fact that something went wrong, since a stack trace can
    leak file paths, query text, or (in the worst case) something like
    an API key if it ever ended up in a variable being repr'd."""
    logger.exception("Unhandled exception in %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})


@app.get("/health")
def health() -> Dict[str, str]:
    """Deliberately unauthenticated: Render's (or any host's) health
    checker has no Clerk token and shouldn't need one just to confirm
    the process is up. Deliberately minimal: no version string, no
    build info, nothing an unauthenticated caller shouldn't see."""
    return {"status": "ok"}


# Same-origin static hosting: the frontend is served by this same
# FastAPI process rather than a separate host. The browser never makes
# a cross-origin request to reach the API, so there is no CORS
# surface for the frontend itself to configure; ALLOWED_ORIGINS stays
# available for any future non-browser or genuinely cross-origin
# client, but the UI doesn't need it.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    """Serves the frontend shell with the Clerk template tokens
    substituted from the environment (see _render_index).

    Deliberately unauthenticated: this is exactly what has to render
    the Clerk sign-in widget for a visitor who isn't signed in yet.

    Note this serves the RENDERED page, never the raw file. The raw
    file is also reachable under /static, but nothing links to it and
    it would be non-functional (unsubstituted tokens) if fetched
    directly."""
    if "html" not in _index_cache:
        _index_cache["html"] = _render_index()
    return HTMLResponse(_index_cache["html"])


@app.get("/config")
def frontend_config() -> Dict[str, str]:
    """Public frontend configuration, read from the server's
    environment at request time.

    Both values here are designed to be public: the publishable key is
    meant to ship in client-side code, and the Clerk frontend host is
    a public CDN hostname. Nothing secret is exposed. What this buys
    is that neither value lives in a committed file any more.

    That matters for a specific reason, found the hard way on
    2026-07-25: these were previously hardcoded into
    static/index.html, so shipping any update to that file silently
    overwrote a working deployment's real values with placeholders and
    broke sign-in entirely. Configuration that differs between
    environments does not belong in a file that gets replaced
    wholesale. Env vars are already how every other deployment-
    specific value here works (ANTHROPIC_API_KEY, CLERK_ISSUER,
    ALLOWED_ORIGINS); this brings the frontend in line with that.

    Deliberately unauthenticated: the sign-in form cannot be rendered
    until the browser has these, so requiring a session to fetch them
    would be circular."""
    return {
        "clerk_publishable_key": os.environ.get("CLERK_PUBLISHABLE_KEY", "").strip(),
        "clerk_frontend_host": _clerk_frontend_host(),
        "feedback_url": os.environ.get("IRIS_FEEDBACK_URL", "").strip(),
    }


# ---------------------------------------------------------------------------
# Authentication, T-9.10. See module docstring and app/clerk_auth.py.
# ---------------------------------------------------------------------------


def get_current_user_id(authorization: str = Header(..., alias="Authorization")) -> str:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="Authorization header must be 'Bearer <token>'.")

    try:
        verifier = get_verifier()
    except RuntimeError as exc:
        logger.error("Auth misconfigured: %s", exc)
        raise HTTPException(status_code=500, detail="Auth is not configured on this server.") from None

    try:
        return verifier.verify(token)
    except ClerkAuthError as exc:
        logger.info("Rejected session token: %s", exc)
        raise HTTPException(status_code=401, detail="Invalid or expired session token.") from None


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------


def _get_session(user_id: str, session_id: str) -> Session:
    try:
        return store.get(user_id, session_id)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found.") from None


@app.post("/sessions")
def create_session(user_id: str = Depends(get_current_user_id)) -> Dict[str, str]:
    session = store.create(user_id)
    return {"session_id": session.session_id, "phase": session.phase.name}


@app.delete("/sessions/{session_id}")
def logout(session_id: str, user_id: str = Depends(get_current_user_id)) -> Dict[str, str]:
    """T-9.11: session-scoped data store. Discards this session's
    registry, term lists, findings, and preferences. No persistence
    beyond this call; the profile export (T-2.14) is the user's own
    copy to carry forward, not a server-side backup."""
    try:
        store.delete(user_id, session_id)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found.") from None
    return {"status": "logged_out", "session_id": session_id}


@app.get("/sessions/{session_id}")
def get_session(session_id: str, user_id: str = Depends(get_current_user_id)) -> Dict[str, Any]:
    session = _get_session(user_id, session_id)
    return {
        "session_id": session.session_id,
        "phase": session.phase.name,
        "active_fact_count": len(session.active_facts()),
        "open_critical_count": len(session.open_criticals()),
    }


class AdvancePhaseRequest(BaseModel):
    target_phase: str  # matches a Phase enum name, e.g. "MASTER_BUILD"


@app.post("/sessions/{session_id}/advance-phase")
def advance_phase(
    session_id: str,
    body: AdvancePhaseRequest,
    user_id: str = Depends(get_current_user_id),
) -> Dict[str, Any]:
    """The gate enforcement point. Every GATE that guards a phase
    transition is checked here, server-side, regardless of what any
    prior model turn claimed. See app/gates.py's module docstring."""
    session = _get_session(user_id, session_id)

    try:
        target = Phase[body.target_phase]
    except KeyError:
        raise HTTPException(status_code=400, detail=f"Unknown phase: {body.target_phase}") from None

    try:
        if target == Phase.MASTER_BUILD:
            require_phase1_disposition(session)
        if target in (Phase.FIT_CHECK, Phase.TAILORING):
            require_registry_populated(session)
        if target == Phase.TAILORING:
            require_fit_check_completed(session)
        if target == Phase.FINAL_REVIEW:
            # Phase 8 is checked once at its own boundary going OUT
            # (delivery), not coming in; require_no_open_criticals is
            # called from the deliver endpoint below instead.
            pass
    except GateBlocked as exc:
        raise HTTPException(status_code=409, detail={"gate_id": exc.gate_id, "message": exc.message}) from None

    session.phase = target
    store.save(session)
    return {"session_id": session.session_id, "phase": session.phase.name}


class DeliverRequest(BaseModel):
    final_text: Optional[str] = None  # T-7.8: the rendered resume/cover-letter text, when checking gap disclosure


@app.post("/sessions/{session_id}/deliver")
def deliver(
    session_id: str,
    body: DeliverRequest = DeliverRequest(),
    user_id: str = Depends(get_current_user_id),
) -> Dict[str, Any]:
    """T-8.18: the actual delivery gate. Nothing before this point
    blocks on open Criticals; this is where it matters. When
    body.final_text is supplied, also runs T-7.8: a Fit Check gap
    that no longer appears in the final text, with no recorded
    acknowledgment, blocks delivery the same way an open Critical
    does. Omitting final_text skips that check rather than failing
    it, so existing callers that don't send it are unaffected."""
    session = _get_session(user_id, session_id)
    try:
        require_no_open_criticals(session)
        if body.final_text is not None:
            require_gap_not_silently_removed(session, body.final_text)
    except GateBlocked as exc:
        raise HTTPException(status_code=409, detail={"gate_id": exc.gate_id, "message": exc.message}) from None
    return {"status": "cleared_for_delivery", "session_id": session.session_id}


# ---------------------------------------------------------------------------
# Chat / tool-use
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Attachments: a place for uploaded file bytes to live server-side, so the
# model never has to receive or type out raw base64 as a tool argument.
# ---------------------------------------------------------------------------

_EXTENSION_TO_FILE_TYPE = {".docx": "docx", ".pdf": "pdf"}


@app.get("/sessions/{session_id}/files/{file_id}")
def download_rendered_file(
    session_id: str,
    file_id: str,
    user_id: str = Depends(get_current_user_id),
) -> Response:
    """Downloads a file produced by a rendering tool (resume docx,
    cover letter docx, Iris Profile markdown). The browser receives a
    real binary response with Content-Disposition: attachment so it
    saves the file under the correct filename automatically — no
    PowerShell, no copy-paste, no manual move required."""
    session = _get_session(user_id, session_id)
    rendered = session.get_rendered_file(file_id)
    if rendered is None:
        raise HTTPException(status_code=404, detail=f"No file with id '{file_id}' on this session.")
    file_bytes = base64.b64decode(rendered.data_base64)
    return Response(
        content=file_bytes,
        media_type=rendered.content_type,
        headers={"Content-Disposition": f'attachment; filename="{rendered.filename}"'},
    )


@app.post("/sessions/{session_id}/attachments")
async def upload_attachment(
    session_id: str,
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id),
) -> Dict[str, str]:
    """Uploads a resume or job posting file, storing it on the session
    and returning an attachment_id. The model calls ingest_document
    (T-0.1) with that id, never with the file's content directly - see
    app.session.Attachment and app.tools.intake.ingest_document for
    why. Rejects anything but .docx/.pdf by extension and anything
    over MAX_UPLOAD_BYTES before ever touching session state."""
    session = _get_session(user_id, session_id)

    filename = file.filename or ""
    suffix = Path(filename).suffix.lower()
    file_type = _EXTENSION_TO_FILE_TYPE.get(suffix)
    if file_type is None:
        raise HTTPException(status_code=400, detail="Only .docx and .pdf files are accepted.")

    raw = await file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)}MB limit.",
        )
    if len(raw) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    attachment = session.add_attachment(
        filename=filename,
        file_type=file_type,
        file_base64=base64.b64encode(raw).decode("ascii"),
    )
    store.save(session)
    return {"attachment_id": attachment.id, "filename": attachment.filename, "file_type": attachment.file_type}


class ChatRequest(BaseModel):
    # `history` is deliberately absent. The transcript lives on the
    # Session, server-side. A client-supplied history is a
    # client-AUTHORED history: it lets a caller forge assistant turns
    # and tool_result blocks asserting that checks already passed,
    # which is exactly the unbacked model self-report spec rule 4.1
    # refuses to treat as enforcement (B1, pre-deploy review
    # 2026-07-25).
    message: str = Field(..., min_length=1, max_length=MAX_MESSAGE_CHARS)
    tool_ids: Optional[List[str]] = None


class RunChecksRequest(BaseModel):
    """Batch check execution request.

    The model calls this instead of invoking each check as a separate
    tool call. Every tool in `tool_ids` must be TOOL-kind (deterministic
    code); HYBRID and JUDGMENT tools are not eligible since they need
    the model's own reasoning to adjudicate. The harness dispatches all
    of them with the shared `inputs` dict and returns every result in
    one response.

    This is the fix for audit latency: 15 sequential model round trips
    (one per slop check) collapsed to a single HTTP call. The model
    receives all findings at once and adjudicates the HYBRID nominees
    in one subsequent turn rather than waiting for each check to come
    back before deciding to call the next one.
    """

    tool_ids: List[str]
    inputs: Dict[str, Any] = Field(default_factory=dict)


@app.post("/sessions/{session_id}/run-checks")
def run_checks(
    session_id: str,
    body: RunChecksRequest,
    user_id: str = Depends(get_current_user_id),
) -> Dict[str, Any]:
    """Dispatches multiple TOOL-kind checks in a single call and returns
    all results together.

    The model calls this endpoint via a single tool_use block whose
    arguments carry the list of check IDs and the shared input dict.
    The harness runs every check and returns the consolidated findings
    list — no per-check round trip, no model waiting between calls.

    Only TOOL-kind items are accepted. GATE, HYBRID, and JUDGMENT items
    are rejected with a 400 so the model cannot accidentally skip
    HYBRID adjudication by treating nominee results as verdicts."""
    session = _get_session(user_id, session_id)

    unknown = [t for t in body.tool_ids if t not in set(registry.ids())]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown tool id(s): {', '.join(sorted(unknown))}")

    wrong_kind = []
    for tid in body.tool_ids:
        tool = registry.get(tid)
        if tool.kind not in (EnforcementKind.TOOL, EnforcementKind.GATE):
            wrong_kind.append(f"{tid} ({tool.kind.name})")
    if wrong_kind:
        raise HTTPException(
            status_code=400,
            detail=f"run-checks only accepts TOOL and GATE items. These are not: {', '.join(wrong_kind)}",
        )

    results = []
    all_passed = True
    for tid in body.tool_ids:
        try:
            result = registry.dispatch_by_id(tid, body.inputs, session=session)
            results.append({
                "tool_id": tid,
                "passed": result.passed,
                "findings": result.findings,
                "data": result.data,
            })
            if not result.passed:
                all_passed = False
        except Exception:
            logger.exception("Tool %s raised in run-checks for session %s", tid, session_id)
            results.append({
                "tool_id": tid,
                "passed": False,
                "findings": [{"severity": "Critical", "issue": f"Tool {tid} failed to run.", "fix": "Check server logs."}],
                "data": {},
            })
            all_passed = False

    return {"all_passed": all_passed, "results": results}


@app.post("/sessions/{session_id}/chat")
def chat(
    session_id: str,
    body: ChatRequest,
    user_id: str = Depends(get_current_user_id),
) -> StreamingResponse:
    """Streams progress as Server-Sent Events rather than returning
    once at the end.

    Everything that can be checked without calling the model
    (rate limit, unknown tool_ids, session lookup) still happens here,
    before the stream starts, and still fails as a normal HTTP error
    with a real status code, exactly as before this change: the
    client can only tell 429/400/404 apart from a streamed response
    by its Content-Type, and there is no reason to make it do that for
    checks that were always synchronous.

    Once streaming starts, the HTTP status is committed to 200 and can
    never change, which is why every failure from that point on
    (upstream API errors, tool-loop exhaustion, anything unexpected)
    is carried as an "error" event inside the stream instead of an
    HTTP status code - see stream_turn's docstring."""
    _chat_rate_limiter.check(user_id)
    session = _get_session(user_id, session_id)

    if body.tool_ids is not None:
        unknown = [t for t in body.tool_ids if t not in set(registry.ids())]
        if unknown:
            raise HTTPException(status_code=400, detail=f"Unknown tool id(s): {', '.join(sorted(unknown))}")

    lock = store.lock_for(user_id, session_id)

    def event_stream():
        # Serialize concurrent turns on one session: stream_turn
        # mutates session state through needs_session tools, and two
        # overlapping turns would interleave those writes (S1). Held
        # for the whole streamed duration, same as it was held for the
        # whole synchronous call before this change - the exclusivity
        # this protects is per turn, not per network round trip.
        with lock:
            session.append_messages([{"role": "user", "content": body.message}])
            try:
                for event in stream_turn(
                    spec_text=_get_spec_text(),
                    messages=list(session.messages),
                    session=session,
                    tool_ids=body.tool_ids,
                ):
                    if event["type"] == "done":
                        session.messages = event["messages"][-MAX_TRANSCRIPT_MESSAGES:]
                        store.save(session)
                        yield _sse_event({"type": "done", "text": event["text"]})
                    else:
                        yield _sse_event(event)
            except Exception:  # noqa: BLE001
                # A safety net for anything stream_turn doesn't already
                # turn into a structured "error" event. Logged in full;
                # the client gets the same generic message main.py's
                # top-level handler already uses for everything else,
                # never exception detail (S3).
                logger.exception("Unhandled exception mid-stream for session %s", session_id)
                yield _sse_event({"type": "error", "detail": "Something went wrong on Iris's end. Try again in a moment."})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _sse_event(event: Dict[str, Any]) -> str:
    return f"data: {json.dumps(event)}\n\n"


# ---------------------------------------------------------------------------
# Debug / introspection
# ---------------------------------------------------------------------------


@app.get("/debug/tools")
def list_tools(user_id: str = Depends(get_current_user_id)) -> List[Dict[str, Any]]:
    """Authenticated, and additionally off in production unless
    IRIS_ENABLE_DOCS is set: it enumerates the whole enforcement
    architecture, which no ordinary user needs."""
    if not _DOCS_ENABLED:
        raise HTTPException(status_code=404, detail="Not found.")
    return [
        {"id": spec.id, "name": spec.name, "kind": spec.kind.value, "blocking": spec.blocking}
        for spec in registry.all()
    ]
