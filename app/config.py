"""
Tuned threshold values.

Amendment protocol rule 5 (docs/iris-spec.md): threshold values tuned
against real documents live in code config, not in the spec. Tuning
these must never require a spec amendment. If you're changing a
number in this file because real documents proved it wrong, that's
exactly what this file is for. If you're changing what a rule means,
that's a spec amendment instead, see docs/iris-spec.md.
"""

from __future__ import annotations

import os

# T-0.2: extraction confidence, evaluated per section, fail-closed.
EXTRACTION_CONFIDENCE = {
    "ocr_min_confidence": 0.85,
    "max_replacement_char_ratio": 0.02,
    "min_role_blocks_with_dates": 2,
    "max_date_parse_failure_ratio": 0.20,
}

# T-3.3: frequency-gated banned terms ("effectively", "directly") are
# ordinary English below this count and a tell above it.
BANNED_TERM_FREQUENCY_THRESHOLD = 2

# T-8.7: per-bullet word limit. A default, not a hard ceiling; see
# T-8.21 for the per-instance authorization path that overrides it.
BULLET_WORD_LIMIT_DEFAULT = 60

# T-7.2 / T-7.13: cover letter length. Same authorization path applies.
COVER_LETTER_WORD_RANGE = (250, 400)

# Fonts and sizes, ATS compliance (T-4.4).
ALLOWED_FONTS = {"Arial", "Calibri", "Helvetica", "Garamond", "Georgia"}
BODY_FONT_SIZE_RANGE = (10, 12)
NAME_FONT_SIZE_RANGE = (11, 14)

# T-4.11: tailored resume length target, a floor not a ceiling.
TAILORED_PAGE_TARGET = (1, 2)

# T-4.11/T-4.12: page-length heuristic. python-docx has no layout
# engine, so this estimates from font size, page geometry, and
# character/line counts rather than a true render. Deliberately
# approximate, decided 2026-07-25 over standing up a real renderer
# (LibreOffice headless) since TAILORED_PAGE_TARGET is already a
# range, not an exact count. margin_in matches app/tools/docx_render.py's
# hardcoded Inches(1); if that ever changes, change it here too. Tune
# these, don't rewrite the formula, if real resumes prove the estimate
# off in one direction. See app/tools/page_estimate.py's module
# docstring for exactly what this does and doesn't model.
PAGE_ESTIMATE = {
    "page_width_in": 8.5,
    "page_height_in": 11.0,
    "margin_in": 1.0,
    "default_font_size_pt": 11.0,
    "char_width_factor": 0.50,
    "line_height_factor": 1.15,
}

# Model id. Env-overridable so a model change does not require a
# redeploy of code (N5, pre-deploy review 2026-07-25).
#
# Changed from claude-sonnet-5 to claude-sonnet-4-6 on 2026-07-26.
# Sonnet 5 was never a deliberate choice for this workload - it just
# fell out of picking "the newest model" with no other setting
# considered. Josh's actual resume work was validated against Sonnet
# 4.6 at Medium effort; Sonnet 5 runs adaptive thinking on by default
# (no explicit `effort` was ever set), which is what caused both the
# truncation and the SDK timeout incidents earlier this same day.
# Iris's workload (tool orchestration and writing judgment against a
# harness that already does the deterministic checking) doesn't call
# for frontier reasoning, and Sonnet 4.6 doesn't spend any tokens on
# thinking unless explicitly asked to. Not deprecated, still fully
# current as of this writing.
MODEL = os.environ.get("IRIS_MODEL", "claude-sonnet-4-6")

# Effort: trades response thoroughness for token/cost efficiency,
# passed as output_config={"effort": EFFORT} on every call (see
# platform.claude.com/docs/en/build-with-claude/effort - it is nested
# under output_config, not a bare top-level parameter). Set explicitly
# rather than left to whatever a given model's own default happens to
# be, so a future model swap can't silently change this again the way
# switching to Sonnet 5 did. "medium" matches the effort level Josh's
# resume work was actually validated against.
EFFORT = os.environ.get("IRIS_EFFORT", "medium")

# Upstream HTTP behavior, pinned rather than inherited.
#
# Correcting the record from the 2026-07-27 review, which claimed there
# was "no retry on upstream 429 or 5xx": not true. The SDK already
# retries 408, 409, 429, and 5xx with exponential backoff, twice by
# default, and already applies a 600s read / 5s connect timeout. Nothing
# was unprotected. These are set explicitly for the same reason EFFORT
# is: a default inherited from a dependency is a default that can change
# under you on an upgrade, silently, and this one governs both cost and
# how long a stuck request holds a session lock.
#
# Retries raised 2 -> 4 because the asymmetry favors it here. A retry
# costs a second or two of backoff; a failure surfacing to the user
# mid-Foundational-Build costs three minutes of work they then repeat.
MODEL_MAX_RETRIES = int(os.environ.get("IRIS_MODEL_MAX_RETRIES", "4"))

# Read timeout is time BETWEEN chunks, not total request duration, since
# every call goes through .messages.stream(). A healthy generation
# delivers tokens continuously, so a long gap means something is wrong
# rather than something is slow: the observed full-turn times are well
# under a minute per API call even on the heaviest phases. 600s let a
# genuinely hung request hold a per-session lock for ten minutes;
# 180s bounds that while staying far above any real inter-chunk gap.
MODEL_READ_TIMEOUT_SECONDS = float(os.environ.get("IRIS_MODEL_READ_TIMEOUT", "180"))
MODEL_CONNECT_TIMEOUT_SECONDS = 10.0

# ---------------------------------------------------------------------------
# Token pricing, USD per million tokens (app/usage.py).
#
# These exist so per-turn cost can be logged alongside per-turn tokens
# without hardcoding a price in the logger. They are the published
# first-party rates for MODEL above (Sonnet 4.6: $3.00 in / $15.00 out
# per MTok). They are NOT authoritative: Anthropic owns the price, this
# is a local copy of it, and a model swap or a price change makes these
# wrong silently. Treat a cost figure in the logs as an estimate for
# comparing interaction types against each other, and the Console for
# what was actually billed.
#
# The two multipliers are the reason this module exists at all. Iris
# pins the spec and every tool schema with cache_control on every single
# call, so the large majority of input tokens on a typical turn are
# cache reads at a tenth of the input rate. Billing the four token
# classes at one flat rate would overstate real input cost by roughly an
# order of magnitude on the cached portion, which is precisely the
# number a pricing decision would be built on.
PRICE_INPUT_PER_MTOK = float(os.environ.get("IRIS_PRICE_INPUT_PER_MTOK", "3.00"))
PRICE_OUTPUT_PER_MTOK = float(os.environ.get("IRIS_PRICE_OUTPUT_PER_MTOK", "15.00"))
# Cache writes cost 1.25x the input rate at the default 5-minute TTL
# (2x at 1h, which Iris does not use); cache reads cost 0.1x.
CACHE_WRITE_MULTIPLIER = float(os.environ.get("IRIS_CACHE_WRITE_MULTIPLIER", "1.25"))
CACHE_READ_MULTIPLIER = float(os.environ.get("IRIS_CACHE_READ_MULTIPLIER", "0.10"))

# ---------------------------------------------------------------------------
# Runtime resource limits (B4/B5, pre-deploy review 2026-07-25).
#
# These are not style thresholds like the ones above; they exist because
# /chat spends real money on every call and the session store lives in
# the memory of one always-on instance. They bound cost and memory, not
# document quality. Tune them, but never remove them: unbounded is the
# failure mode they exist to prevent.
# ---------------------------------------------------------------------------

# Longest single user message accepted by /chat.
MAX_MESSAGE_CHARS = 40_000  # raised from 20_000 — a full foundational resume
# paste (tested at ~31K chars) was hitting the old limit and returning
# the generic "something went wrong" error. 40K covers large resumes
# with headroom for JD pastes alongside them.

# Longest extracted-document text handed to the model in one tool result.
# Raised from 100_000 (2026-07-27): a multi-year performance review export
# (the "performance document" entry path, spec Phase 0) is a real document
# that can legitimately run several hundred pages, and 100K chars was
# truncating well inside that range. A resume or JD anywhere near even this
# larger cap is still far more likely to be a paste error or an injection
# payload than a real document (see app/untrusted_text.py, which truncates
# and says so rather than silently dropping the excess either way).
MAX_INGEST_TEXT_CHARS = 400_000

# Largest extracted text handed to the model INLINE in an ingest result.
#
# The distinction matters because a tool result does not just get read
# once, it is appended to the transcript and re-sent as input on every
# subsequent call for the life of the session. At the 400,000-char
# ceiling above that is ~100,000 tokens per call, roughly half of
# Sonnet's context window consumed by a single upload, billed on every
# turn (cache softens but does not remove this: writes bill at 1.25x and
# the TTL is five minutes).
#
# 60,000 chars (~15,000 tokens) is chosen to sit above any real resume,
# the largest tested is ~31,000 chars, so the resume path behaves
# EXACTLY as it did before this split and nothing about the validated
# flow changes. Documents past it (performance exports, spec Phase 0)
# get a preview plus paging via read_attachment_text (T-0.10), which
# reads the full cached text server-side. That also matches how those
# documents are meant to be worked anyway: role by role, not in one
# pass.
INLINE_EXTRACT_CHARS = 60_000

# Turns retained in a session transcript. Oldest are dropped first.
MAX_TRANSCRIPT_MESSAGES = 100

# Backstop on total transcript size, in characters, applied after the
# message-count cap. A count-only cap bounds the number of turns but not
# their size: 100 messages carrying large tool results is unbounded
# context. ~250,000 chars is ~62,000 tokens, leaving comfortable room
# under the model's window for the system prompt, tool schemas, and a
# full response. Oldest messages are dropped first, same policy as the
# count cap.
MAX_TRANSCRIPT_CHARS = 250_000

# Idle time before a session is evicted. In-memory storage means an
# abandoned session is retained for the life of the process otherwise.
SESSION_TTL_SECONDS = 8 * 60 * 60

# Hard ceiling on concurrently stored sessions per user. Lowered from 20
# on 2026-07-27: sessions are cheap except for the attachment bytes they
# hold, and 20 multiplied against the per-session attachment budget below
# into a per-user worst case far larger than the instance has RAM for.
# Eight concurrent in-flight application pipelines per user is already
# generous; least-recently-used sessions are evicted past this.
MAX_SESSIONS_PER_USER = 8

# Uploaded file (docx/pdf) limits.
#
# These bound REAL MEMORY on a single always-on instance, not just
# request size: attachment bytes live in the in-memory session store
# until the session expires (SESSION_TTL_SECONDS) or is evicted. Before
# 2026-07-27 only per-file size and per-session COUNT were capped, which
# multiplied out to ~2.8 GB of attachments for one user against a
# 512 MB Render Starter instance. Roughly four max-size uploads was an
# out-of-memory restart, and because the store is in-memory, that
# restart would have dropped every other user's live session with it.
#
# Three layers now, because any one of them alone leaves a hole:
#   - per file: a single upload cannot be enormous
#   - per session, in BYTES: many medium files cannot add up to the same
#     thing, which a count-only cap allowed
#   - per user: bounded by MAX_SESSIONS_PER_USER above
# Worst case per user is now MAX_SESSIONS_PER_USER * the per-session
# byte budget, ~96 MB, rather than ~2.8 GB.
#
# 6 MB per file is deliberately not smaller: the performance-document
# entry path (spec Phase 0) accepts multi-hundred-page review exports,
# and a text-heavy PDF that size runs a few MB. Sizing this below a real
# perf doc would break the feature to save memory the byte budget
# already bounds.
MAX_UPLOAD_BYTES = 6 * 1024 * 1024  # 6 MB
MAX_ATTACHMENTS_PER_SESSION = 10  # oldest evicted first past this
MAX_ATTACHMENT_BYTES_PER_SESSION = 12 * 1024 * 1024  # 12 MB, oldest evicted first past this

# Maximum tokens in a single model response. History: 4096 -> 8192 ->
# 16000 on 2026-07-26, each bump chasing truncation on real audits.
# Truncation recurred at 16000 the next morning, which pointed at the
# actual mechanism rather than "audits are long": Claude Sonnet 5 runs
# with adaptive thinking on by default, and max_tokens is a hard cap
# on thinking PLUS visible response text combined, not just the text.
# Nothing in claude_client.py sets an effort or thinking parameter, so
# every call runs at Sonnet 5's default (high effort, adaptive
# thinking on) with zero budget set aside for it. Sonnet 5's tokenizer
# also produces roughly 30% more tokens than Sonnet 4.6 for the same
# text, so the "16000" figure (extrapolated from an old Hermes-era
# Sonnet 4.6 number) undershot from two directions at once. Raised
# here to 32000, still a small fraction of Sonnet 5's real 128k output
# ceiling, to give thinking and tool calls real headroom rather than
# guessing again at the next-smallest number. If cost or latency ever
# matters more than headroom, the other lever documented by Anthropic
# for this exact symptom is dropping effort from its "high" default to
# "medium" in the messages.create() call - not done here, since that
# trades audit thoroughness for tokens and is a product call, not a
# bug fix. Env-overridable so this can be tuned without a code change.
MAX_RESPONSE_TOKENS = int(os.environ.get("IRIS_MAX_RESPONSE_TOKENS", "32000"))

# Findings returned by one run_batch_checks call.
#
# Added 2026-07-28 after a live failure. A batch run against a cached
# 338-page performance export returned 5,002 findings in a single tool
# result: 850,613 characters, roughly 212,000 tokens, which exceeds
# Sonnet's entire 200,000-token context window before the spec, the tool
# schemas, or any conversation history are added. The request was
# rejected with an HTTP 400 and the session could not continue.
#
# This is the hole left by INLINE_EXTRACT_CHARS above. That bounded what
# ingest_document INLINES, so a large document no longer arrives whole.
# It did nothing about what the CHECKS return: run_batch_checks resolves
# the full cached text server-side from attachment_id and every check
# reports every hit, each one quoting the span it flagged. Reading the
# document was bounded; checking it was not.
#
# Per-check rather than only overall, so one noisy check (an em-dash
# sweep over 400,000 characters) cannot crowd every other check out of
# the result. Findings are kept in severity order, so a Critical is
# never dropped in favour of a Low.
MAX_FINDINGS_PER_CHECK = 20
MAX_FINDINGS_PER_BATCH = 100

# Per-user /chat rate limit: max calls within the rolling window.
#
# Raised from 30 on 2026-07-28: confirmed live, a real new-user
# walkthrough on the from-scratch entry path (role-by-role elicitation,
# spec Phase 0) hit this mid-session during ordinary use, not abuse, and
# was stuck for the rest of the rolling hour with no way to continue.
# The 2026-07-27 review flagged this as plausible (R-3); this is the
# live confirmation. 30/hour was sized as an abuse ceiling, not against
# a real full pipeline session, which routinely runs well past it once
# audit discussion, several rounds of Foundational Build elicitation,
# fit check, tailoring, and cover letter revisions are all one
# conversation. 100 stays a real ceiling, a genuinely runaway loop still
# hits it fast, while giving a normal thorough session comfortable
# headroom. Env-overridable so it can be tuned without a redeploy next
# time.
CHAT_RATE_LIMIT_CALLS = int(os.environ.get("IRIS_CHAT_RATE_LIMIT_CALLS", "100"))
CHAT_RATE_LIMIT_WINDOW_SECONDS = 60 * 60

# How long the /chat SSE stream can go with no new event before it
# sends a bare ": heartbeat" comment line to keep the connection alive.
# A single slow model call (a HYBRID check the model is deliberating
# over, or a long final response) can go multiple minutes with nothing
# new to tell the client - confirmed 2026-07-26: the server kept
# working with no error logged, but the browser's connection to it was
# dropped anyway, almost certainly by an intermediary (Render's proxy,
# a corporate network) treating the silence as a dead connection.
# Comment lines are invisible to the SSE event parser (it only looks
# for "data: " lines), so this is pure keep-alive, not a new event
# type the frontend needs to handle.
SSE_HEARTBEAT_INTERVAL_SECONDS = int(os.environ.get("IRIS_SSE_HEARTBEAT_INTERVAL_SECONDS", "15"))
