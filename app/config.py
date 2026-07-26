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
MAX_MESSAGE_CHARS = 40_000  # raised from 20_000 — a full master resume
# paste (tested at ~31K chars) was hitting the old limit and returning
# the generic "something went wrong" error. 40K covers large resumes
# with headroom for JD pastes alongside them.

# Longest extracted-document text handed to the model in one tool result.
# A resume or JD well over this is far more likely to be a paste error or
# an injection payload than a real document (see app/untrusted_text.py).
MAX_INGEST_TEXT_CHARS = 100_000

# Turns retained in a session transcript. Oldest are dropped first.
MAX_TRANSCRIPT_MESSAGES = 100

# Idle time before a session is evicted. In-memory storage means an
# abandoned session is retained for the life of the process otherwise.
SESSION_TTL_SECONDS = 8 * 60 * 60

# Hard ceiling on concurrently stored sessions per user.
MAX_SESSIONS_PER_USER = 20

# Uploaded file (docx/pdf) limits. A resume or JD file has no business
# being large; a very large upload is far more likely to be the wrong
# file or an abuse attempt than a real document.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_ATTACHMENTS_PER_SESSION = 10  # oldest evicted first past this

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

# Per-user /chat rate limit: max calls within the rolling window.
CHAT_RATE_LIMIT_CALLS = 30
CHAT_RATE_LIMIT_WINDOW_SECONDS = 60 * 60
