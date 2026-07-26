"""
Wraps the Anthropic Messages API with native tool-use.

Requires `pip install anthropic` and ANTHROPIC_API_KEY in the
environment; this module is not exercised by the sandbox that wrote
it, since that sandbox has no network and no SDK installed. Run
tests/test_claude_client_smoke.py locally once both are available, it
sends one real request and confirms the loop terminates.

The spec text is sent as the first system block with
cache_control: {"type": "ephemeral"}, per spec section 9.1 / T-9.1:
"Spec load and prompt caching... cached globally, since one artifact
serves every user." A cache hit costs a fraction of the input tokens
a cold read would; on a document this size, that is the difference
between routine and expensive.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

import anthropic

from app.config import MAX_RESPONSE_TOKENS, MODEL
from app.enforcement import registry
from app.session import Session

logger = logging.getLogger("iris.claude")


def _client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Set it in the environment or a "
            ".env file before calling run_turn()."
        )
    return anthropic.Anthropic(api_key=api_key)


class UpstreamModelError(RuntimeError):
    """A failure reported by the Anthropic API itself, as opposed to a
    bug in this harness.

    These are ordinary operating conditions, not exceptional ones: the
    API can be overloaded, rate-limit us, or reject a request whose
    accumulated context has grown past the model's window. Before this
    existed they all escaped as unhandled exceptions and reached the
    user as a bare 500 saying "something went wrong on Iris's end,"
    which is both unhelpful and, for an upstream outage or a
    context-size problem, not even accurate."""

    def __init__(self, status_code, message: str):
        self.status_code = status_code
        super().__init__(message)


def _blocks_to_plain(blocks) -> List[Dict[str, Any]]:
    """Convert SDK content blocks to plain JSON-safe dicts.

    The transcript is persisted on the Session and round-tripped into
    later API calls, so it must not hold SDK objects: their serialized
    shape is an implementation detail that an SDK upgrade is free to
    change, and stored state would change shape with it (B2,
    pre-deploy review 2026-07-25)."""
    plain: List[Dict[str, Any]] = []
    for block in blocks:
        if block.type == "text":
            plain.append({"type": "text", "text": block.text})
        elif block.type == "tool_use":
            plain.append(
                {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
            )
        else:
            # Unknown future block type: keep something faithful rather
            # than dropping the turn silently.
            plain.append(json.loads(block.model_dump_json()) if hasattr(block, "model_dump_json") else {"type": str(block.type)})
    return plain


class ToolLoopExhausted(RuntimeError):
    """Raised when a turn hits max_tool_iterations. A distinct type so
    the route can answer 409 with something actionable rather than
    letting a bare RuntimeError become an opaque 500 (S5)."""

    def __init__(self, iterations: int, messages: List[Dict[str, Any]]):
        self.iterations = iterations
        self.messages = messages
        super().__init__(
            f"Tool loop did not terminate within {iterations} iterations."
        )


def run_turn(
    spec_text: str,
    messages: List[Dict[str, Any]],
    session: Optional[Session] = None,
    tool_ids: Optional[List[str]] = None,
    max_tokens: int = MAX_RESPONSE_TOKENS,
    max_tool_iterations: int = 12,
) -> Dict[str, Any]:
    """Run one user turn to completion, dispatching every tool call the
    model makes until it produces a final text response or the
    iteration cap is hit.

    `session`, when provided, is threaded through to
    registry.dispatch() so needs_session tools (fact-lock validation,
    value-match against the registry) receive real session state. It
    is never placed in the messages sent to the model; the model has
    no way to read or forge it.

    Returns {"text": str, "messages": list} where `messages` is the
    full updated transcript, ready to be stored and passed back in on
    the next call.
    """
    client = _client()
    tools = registry.claude_schemas(tool_ids)
    working_messages = list(messages)

    for _ in range(max_tool_iterations):
        # Logged at every round trip because accumulated context is the
        # most likely cause of a request that worked earlier in a
        # conversation and fails later: tool results (an ingested
        # document can be up to MAX_INGEST_TEXT_CHARS on its own) stay
        # in the transcript and are resent every turn. When a chat
        # starts failing partway through a session, this is the first
        # number to look at.
        approx_chars = sum(len(str(m.get("content", ""))) for m in working_messages)
        logger.info(
            "Claude call: %d messages, ~%d chars of transcript, %d tools",
            len(working_messages),
            approx_chars,
            len(tools),
        )

        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=max_tokens,
                system=[
                    {
                        "type": "text",
                        "text": spec_text,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                tools=tools,
                messages=working_messages,
            )
        except anthropic.APIError as exc:
            status = getattr(exc, "status_code", None)
            logger.exception("Anthropic API call failed (status=%s)", status)
            raise UpstreamModelError(status, str(exc)) from exc

        logger.info(
            "Claude responded: stop_reason=%s, blocks=%s",
            response.stop_reason,
            [block.type for block in response.content],
        )

        working_messages = working_messages + [
            {"role": "assistant", "content": _blocks_to_plain(response.content)}
        ]

        if response.stop_reason != "tool_use":
            final_text = "".join(
                block.text for block in response.content if block.type == "text"
            )

            # A truncated response is not a successful one. Hitting the
            # output cap mid-answer produces stop_reason="max_tokens",
            # and if the cut landed before any complete text block this
            # used to return {"text": ""} with a 200, which the UI
            # rendered as an empty bubble: the user saw the assistant
            # reply with nothing and had no way to tell whether it
            # failed, was still working, or had genuinely said nothing.
            if response.stop_reason == "max_tokens":
                logger.warning(
                    "Response hit the %d-token output cap (%d chars of text recovered)",
                    max_tokens,
                    len(final_text),
                )
                notice = (
                    "\n\n[This response was cut off at the output limit. Ask for it in "
                    "smaller pieces, for example one section or one check at a time.]"
                )
                return {"text": (final_text + notice) if final_text else notice.strip(), "messages": working_messages}

            if not final_text.strip():
                # Any other empty completion is a real anomaly worth
                # surfacing rather than rendering as silence.
                logger.error(
                    "Empty completion with stop_reason=%s and blocks=%s",
                    response.stop_reason,
                    [block.type for block in response.content],
                )
                return {
                    "text": (
                        "The assistant returned an empty response. Try rephrasing, or "
                        "start a new session if this keeps happening."
                    ),
                    "messages": working_messages,
                }

            return {"text": final_text, "messages": working_messages}

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            try:
                result = registry.dispatch(block.name, block.input, session=session)
                content = {
                    "passed": result.passed,
                    "findings": result.findings,
                    "data": result.data,
                }
            except Exception:  # noqa: BLE001
                # Logged in full server-side; the model gets the tool
                # name and nothing else. Raw exception text used to go
                # into the transcript and back out to the client, which
                # contradicted main.py's generic-500 policy and could
                # carry internal detail (S3, pre-deploy review
                # 2026-07-25).
                logger.exception("Tool %s raised during dispatch", block.name)
                content = {
                    "error": f"Tool {block.name} failed to run. The harness logged the detail.",
                }
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    # json.dumps, not str(): str() emits a Python repr with
                    # single quotes, which is not valid JSON for the model
                    # to parse (S7).
                    "content": json.dumps(content, default=str),
                }
            )

        working_messages = working_messages + [{"role": "user", "content": tool_results}]

    raise ToolLoopExhausted(max_tool_iterations, working_messages)


def _humanize_tool_name(name: str) -> str:
    """'check_headline_skills_backed' -> 'check headline skills backed'.

    Deliberately not a curated display-name lookup table: with 90+
    tools, a table needs updating every time one is added or renamed,
    and silently falls out of sync when someone forgets. This can
    never drift, at the cost of a name that reads as code rather than
    prose."""
    return name.replace("_", " ")


def stream_turn(
    spec_text: str,
    messages: List[Dict[str, Any]],
    session: Optional[Session] = None,
    tool_ids: Optional[List[str]] = None,
    max_tokens: int = MAX_RESPONSE_TOKENS,
    max_tool_iterations: int = 12,
):
    """Same job as run_turn, structured as a generator that yields
    progress events instead of returning once at the end, so a caller
    (main.py's /chat route, via SSE) can show the user what's
    happening while a multi-tool-call turn is still in flight rather
    than a static "thinking" indicator with no information behind it.

    Deliberately a separate function rather than a refactor of
    run_turn: run_turn is exercised directly by
    tests/test_claude_client_smoke.py, the one test in this codebase
    that costs real money and needs a live network, and changing it
    late in a session that has already caused two production outages
    tonight is not a risk worth taking for what is fundamentally a
    duplicate loop. The two will drift if either changes without the
    other; consolidating them behind a shared core is worth doing
    later, deliberately, not as a rider on this change.

    Yields dicts, always with a "type" key:
      {"type": "status", "message": str}
      {"type": "tool_call", "tool": str}
      {"type": "tool_result", "tool": str, "passed": bool}
      {"type": "done", "text": str, "messages": list}
      {"type": "error", "detail": str}

    An "error" or "done" event is always the last one yielded. Known
    failure modes (UpstreamModelError, ToolLoopExhausted) are caught
    here and turned into an "error" event rather than raised, because
    by the time this is driving an SSE response the HTTP status code
    is already committed to 200; an exception escaping after that
    point can only become a broken stream, not a clean HTTP error."""
    try:
        client = _client()
    except RuntimeError as exc:
        yield {"type": "error", "detail": str(exc)}
        return

    tools = registry.claude_schemas(tool_ids)
    working_messages = list(messages)

    for _ in range(max_tool_iterations):
        approx_chars = sum(len(str(m.get("content", ""))) for m in working_messages)
        logger.info(
            "Claude call (streaming): %d messages, ~%d chars of transcript, %d tools",
            len(working_messages),
            approx_chars,
            len(tools),
        )
        yield {"type": "status", "message": "Thinking..."}

        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=max_tokens,
                system=[
                    {
                        "type": "text",
                        "text": spec_text,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                tools=tools,
                messages=working_messages,
            )
        except anthropic.APIError as exc:
            status = getattr(exc, "status_code", None)
            logger.exception("Anthropic API call failed (status=%s)", status)
            yield {"type": "error", "detail": _upstream_error_detail(status)}
            return

        logger.info(
            "Claude responded (streaming): stop_reason=%s, blocks=%s",
            response.stop_reason,
            [block.type for block in response.content],
        )

        working_messages = working_messages + [
            {"role": "assistant", "content": _blocks_to_plain(response.content)}
        ]

        if response.stop_reason != "tool_use":
            final_text = "".join(
                block.text for block in response.content if block.type == "text"
            )

            if response.stop_reason == "max_tokens":
                logger.warning(
                    "Response hit the %d-token output cap (%d chars of text recovered)",
                    max_tokens,
                    len(final_text),
                )
                notice = (
                    "\n\n[This response was cut off at the output limit. Ask for it in "
                    "smaller pieces, for example one section or one check at a time.]"
                )
                yield {
                    "type": "done",
                    "text": (final_text + notice) if final_text else notice.strip(),
                    "messages": working_messages,
                }
                return

            if not final_text.strip():
                logger.error(
                    "Empty completion with stop_reason=%s and blocks=%s",
                    response.stop_reason,
                    [block.type for block in response.content],
                )
                yield {
                    "type": "done",
                    "text": (
                        "The assistant returned an empty response. Try rephrasing, or "
                        "start a new session if this keeps happening."
                    ),
                    "messages": working_messages,
                }
                return

            yield {"type": "done", "text": final_text, "messages": working_messages}
            return

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            display_name = _humanize_tool_name(block.name)
            yield {"type": "tool_call", "tool": display_name}
            try:
                result = registry.dispatch(block.name, block.input, session=session)
                content = {
                    "passed": result.passed,
                    "findings": result.findings,
                    "data": result.data,
                }
                yield {"type": "tool_result", "tool": display_name, "passed": result.passed}
            except Exception:  # noqa: BLE001
                logger.exception("Tool %s raised during dispatch", block.name)
                content = {
                    "error": f"Tool {block.name} failed to run. The harness logged the detail.",
                }
                yield {"type": "tool_result", "tool": display_name, "passed": False}
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(content, default=str),
                }
            )

        working_messages = working_messages + [{"role": "user", "content": tool_results}]

    yield {
        "type": "error",
        "detail": "The assistant could not complete this turn. Rephrase and try again.",
    }


def _upstream_error_detail(status_code: Optional[int]) -> str:
    """The same categorized messages the non-streaming /chat error
    path (main.py, batch 19) used, moved here so stream_turn can
    produce them without main.py needing to catch UpstreamModelError
    after the SSE response has already started."""
    if status_code == 429:
        return "The model API is rate-limiting requests right now. Wait a moment and try again."
    if status_code is not None and 500 <= status_code < 600:
        return "The model API is having trouble right now. Wait a moment and try again."
    if status_code == 400:
        return (
            "The model API rejected this request. This conversation may have grown too "
            "long to continue; start a new session to reset it."
        )
    return "Could not reach the model API. Try again in a moment."
