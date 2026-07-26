"""
Core enforcement types.

Every capability in docs/iris-tool-list.md is classified into one of
five kinds (spec section 4). This module gives those kinds a runtime
representation: a ToolSpec carries its id, its declared kind, and the
Python function that actually performs the check.

Two things this registry is deliberately built to prevent, both named
in the spec:

  - Spec rule 4.1: a model asserting compliance without an underlying
    deterministic scan is never sufficient to clear a Critical or
    Pedantic finding. Registering a tool here means there is a real
    function behind the claim, not a prompt asking the model to
    self-report.

  - The cross-file drift the two-document split introduced (Decision
    Log, 2026-07-24). tests/test_spec_sync.py parses
    docs/iris-tool-list.md and checks every id registered here against
    it, so a tool whose declared kind disagrees with the document
    fails a test rather than silently drifting.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class EnforcementKind(str, Enum):
    TOOL = "TOOL"
    GATE = "GATE"
    HYBRID = "HYBRID"
    JUDGMENT = "JUDGMENT"
    HUMAN = "HUMAN"


@dataclass
class ToolResult:
    """Return type for every registered check.

    passed=False does not necessarily mean "block". Only GATE-kind
    tools stop a phase transition on failure (see app/gates.py); a
    TOOL or HYBRID finding surfaces to the review pass without
    stopping anything by itself.
    """

    passed: bool
    findings: List[Dict[str, Any]] = field(default_factory=list)
    data: Dict[str, Any] = field(default_factory=dict)


HandlerFn = Callable[..., ToolResult]


@dataclass
class ToolSpec:
    id: str  # e.g. "T-3.1", matches docs/iris-tool-list.md exactly
    name: str  # function name exposed to Claude's tool-use API
    description: str  # shown to Claude verbatim; keep it accurate, it IS the contract
    kind: EnforcementKind
    input_schema: Dict[str, Any]
    handler: HandlerFn
    blocking: bool = False  # True marks a GATE the harness enforces server-side
    needs_session: bool = False  # see dispatch(): session is injected, never model-supplied


class DuplicateToolError(ValueError):
    pass


class ToolNotFoundError(KeyError):
    pass


class ToolRegistry:
    def __init__(self) -> None:
        self._by_id: Dict[str, ToolSpec] = {}
        self._by_name: Dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.id in self._by_id:
            raise DuplicateToolError(f"Tool id already registered: {spec.id}")
        if spec.name in self._by_name:
            raise DuplicateToolError(f"Tool name already registered: {spec.name}")
        self._by_id[spec.id] = spec
        self._by_name[spec.name] = spec

    def get(self, tool_id: str) -> ToolSpec:
        try:
            return self._by_id[tool_id]
        except KeyError:
            raise ToolNotFoundError(tool_id) from None

    def get_by_name(self, name: str) -> ToolSpec:
        try:
            return self._by_name[name]
        except KeyError:
            raise ToolNotFoundError(name) from None

    def all(self) -> List[ToolSpec]:
        return list(self._by_id.values())

    def ids(self) -> List[str]:
        return list(self._by_id.keys())

    def claude_schemas(self, tool_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Build the `tools` array for a Messages API call.

        Anthropic's tool schema field is `input_schema`, not `parameters`;
        there is no function-wrapper the way some other providers use.
        """
        specs = self.all() if tool_ids is None else [self.get(i) for i in tool_ids]
        return [
            {
                "name": s.name,
                "description": f"[{s.id}] {s.description}",
                "input_schema": s.input_schema,
            }
            for s in specs
        ]

    def dispatch(self, name: str, tool_input: Dict[str, Any], session: Any = None) -> ToolResult:
        """Run a tool by name.

        `session` is supplied by the harness route that already
        authenticated the request, never taken from tool_input. A tool
        marked needs_session receives it as a keyword argument in
        addition to whatever the model passed; a tool that isn't
        marked needs_session never sees it at all, so a text-only
        check like check_em_dash cannot accidentally be handed session
        state it has no schema for. This is spec 7.6 / T-9.12 in code:
        the model's arguments can request an action, they can never
        supply an identity to act as.
        """
        spec = self.get_by_name(name)
        if spec.needs_session:
            if session is None:
                raise ValueError(
                    f"Tool {name} ({spec.id}) requires session context, "
                    "but dispatch() was called without one. This is a "
                    "harness bug, not a model error: the caller must "
                    "supply the authenticated session."
                )
            return spec.handler(session=session, **tool_input)
        return spec.handler(**tool_input)

    def dispatch_by_id(self, tool_id: str, tool_input: Dict[str, Any], session: Any = None) -> ToolResult:
        """Run a tool by its T-x.y id rather than its function name.

        Used by the /run-checks batch endpoint, which receives tool IDs
        from the model rather than names. Identical session-injection
        semantics to dispatch()."""
        spec = self.get(tool_id)
        # Filter tool_input to only the keys the tool actually accepts,
        # so a batch call with a superset of inputs (e.g. both `text`
        # and `roles`) does not break tools that only take one of them.
        import inspect
        accepted = set(inspect.signature(spec.handler).parameters.keys()) - {"session"}
        filtered = {k: v for k, v in tool_input.items() if k in accepted}
        if spec.needs_session:
            if session is None:
                raise ValueError(
                    f"Tool {tool_id} requires session context but none was supplied."
                )
            return spec.handler(session=session, **filtered)
        return spec.handler(**filtered)


registry = ToolRegistry()


def tool(
    id: str,
    name: str,
    description: str,
    kind: EnforcementKind,
    input_schema: Dict[str, Any],
    blocking: bool = False,
    needs_session: bool = False,
):
    """Decorator: registers a plain Python function as a ToolSpec.

    The decorated function is left callable exactly as written, so the
    harness can invoke it directly for mandatory server-side
    verification (see app/gates.py) as well as exposing it to Claude
    as a tool. Same function, two call paths, one implementation.
    """

    def decorator(fn: HandlerFn) -> HandlerFn:
        registry.register(
            ToolSpec(
                id=id,
                name=name,
                description=description,
                kind=kind,
                input_schema=input_schema,
                handler=fn,
                blocking=blocking,
                needs_session=needs_session,
            )
        )
        return fn

    return decorator
