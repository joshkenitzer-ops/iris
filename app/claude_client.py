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

from app.config import MODEL
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
    max_tokens: int = 4096,
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

        working_messages = working_messages + [
            {"role": "assistant", "content": _blocks_to_plain(response.content)}
        ]

        if response.stop_reason != "tool_use":
            final_text = "".join(
                block.text for block in response.content if block.type == "text"
            )
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
