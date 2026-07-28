"""Structural guard: enforcement that nothing calls is not enforcement.

Five separate times, this codebase has shipped correct, fully
unit-tested logic that no production code path ever invoked:

  1. The delivery gates (T-8.18, T-7.8) ran only inside POST /deliver,
     which the frontend never calls. Resumes with open Criticals were
     downloadable.
  2. The download route was broken two independent ways with no
     coverage at all.
  3. estimate_page_count (T-4.11) and T-4.12 were written and
     referenced by nothing; a six-page resume shipped.
  4. require_no_unresolved_markers (T-6.14) had zero callers, so
     "[ADD METRIC: ...]" could reach a delivered document.
  5. bootstrapSession() in app.js was defined, mentioned once in a
     comment, and never called, so a page reload abandoned a live
     session.

Each was found by a human noticing, after it had already shipped. The
common shape is not a bug in any of these functions, it is that nothing
in the build fails when a check has no caller. This file is that
failure.

Why AST and not grep: a mention in a docstring or a comment must not
count as a caller. require_turn_completion is referenced by name in a
comment inside gates.py and is called by nothing; a grep-based guard
would score it reachable and miss exactly the case it exists to catch.
Only an ast.Call node counts.

Adding a gate to an allowlist below is a deliberate, reviewed act that
requires writing down why. That is the point: an exemption should cost
a sentence of justification, not a silent skip.
"""

import ast
import pathlib
import re
import unittest

APP = pathlib.Path("app")
GATES_FILE = APP / "gates.py"
MAIN_FILE = APP / "main.py"
APP_JS = pathlib.Path("static") / "app.js"


# ---------------------------------------------------------------------------
# Gate functions
# ---------------------------------------------------------------------------

# A gate may be exempt only with a stated reason. Anything here is
# asserted to be deliberately unenforced, not merely forgotten.
GATE_EXEMPTIONS = {
    "require_no_fabricated_compensation_range": (
        "T-5.8 guards a market compensation search that does not exist yet. "
        "No tool performs one and nothing can supply search_succeeded. "
        "Premature, not unwired: wire it when the feature lands."
    ),
    "require_turn_completion": (
        "T-9.6 belongs to the spec amendment protocol, which per README "
        "binds the development harness and explicitly does NOT bind Iris at "
        "runtime. Iris has no authority to amend the spec, so there is no "
        "runtime turn for this to complete."
    ),
    "require_amendment_confirmed": (
        "T-9.5, same reasoning as T-9.6: amendment protocol, development "
        "harness only, never reached by a running session."
    ),
    # The three below are called ONLY from advance_phase, whose route
    # the frontend never invokes. This guard counts that as unreachable
    # on purpose (see _dead_route_handler_names), which is what makes it
    # able to catch the original incident rather than merely describe
    # it. They are listed here as known and reasoned, not as fixed.
    "require_phase1_disposition": (
        "T-1.8 blocks Phase 2 while a Phase 1 Critical is undispositioned, and "
        "its only caller is the dead /advance-phase route. Not wired to the "
        "render chokepoint because require_no_open_criticals (T-8.18) already "
        "runs there and is strictly stronger: it blocks delivery on ANY open "
        "Critical regardless of phase. The user-facing protection is intact; "
        "what is missing is the phase-boundary version of it."
    ),
    "require_fit_check_completed": (
        "T-5.1 reads session.fit_check_completed, which NOTHING sets to True: "
        "Phase 5 has zero registered tools. Wiring it at the render chokepoint "
        "would not restore a dormant protection, it would permanently block "
        "every tailored resume download. See "
        "test_nothing_sets_fit_check_completed_to_true in "
        "test_delivery_gate_on_render.py, which fails once a setter exists."
    ),
    "require_registry_populated": (
        "T-5.2 depends on the model having called extract_facts_into_registry. "
        "Only caller is the dead /advance-phase route. Deliberately NOT moved "
        "to the render chokepoint: a gate that turns a missed model call into "
        "an undownloadable document is worse than the risk it covers."
    ),
}


def _gate_function_names() -> set:
    tree = ast.parse(GATES_FILE.read_text(encoding="utf-8"))
    return {
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name.startswith("require_")
    }


def _dead_route_handler_names() -> set:
    """Handler functions in main.py whose route the frontend never
    calls, per the DEAD entries in ROUTE_EXEMPTIONS.

    These exist so a call site INSIDE one of them does not count as
    reachability. That distinction is the whole point of this guard
    rather than a nice refinement of it: in the original incident the
    delivery gates WERE called, from the /deliver handler, and /deliver
    is a route the product never invokes. A guard that accepts any call
    site would have scored those gates reachable and passed while
    resumes with open Critical findings shipped."""
    dead_keys = [k for k, reason in ROUTE_EXEMPTIONS.items() if "DEAD ROUTE" in reason]
    tree = ast.parse(MAIN_FILE.read_text(encoding="utf-8"))
    dead_handlers = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            route = next(
                (a.value for a in decorator.args if isinstance(a, ast.Constant) and isinstance(a.value, str)),
                None,
            )
            if route and any(route == k or route.endswith(k) for k in dead_keys):
                dead_handlers.add(node.name)
    return dead_handlers


def _called_names_in_app() -> set:
    """Every function name called from a REACHABLE place in app/.

    ast.Call only. A name in a comment, a docstring, an import, or a
    string literal is not a caller, and treating it as one is how a
    guard like this quietly stops working: require_turn_completion is
    named in a comment inside gates.py and called by nothing.

    Calls made from inside a dead-route handler are excluded, so a gate
    whose only caller is an unreachable endpoint still counts as
    unreachable. Verified by removing the delivery gates from the render
    chokepoint and confirming this guard fails."""
    dead_handlers = _dead_route_handler_names()
    called = set()
    for path in APP.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in dead_handlers and path == MAIN_FILE:
                continue  # walked separately below, and deliberately not counted
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if name:
                called.add(name)
    # ast.walk does not respect the `continue` above (it flattens the
    # whole tree), so subtract the dead handlers' own call sites
    # explicitly.
    if dead_handlers:
        main_tree = ast.parse(MAIN_FILE.read_text(encoding="utf-8"))
        dead_only = set()
        reachable_elsewhere = set()
        for node in ast.walk(main_tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            target = dead_only if node.name in dead_handlers else reachable_elsewhere
            for inner in ast.walk(node):
                if isinstance(inner, ast.Call):
                    func = inner.func
                    name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
                    if name:
                        target.add(name)
        # A name called ONLY from dead handlers, and nowhere else in the
        # entire app, is not reachable.
        called -= {
            name for name in dead_only
            if name not in reachable_elsewhere and not _called_outside_main(name, dead_handlers)
        }
    return called


def _called_outside_main(name: str, dead_handlers: set) -> bool:
    """Whether `name` is called anywhere in app/ other than main.py's
    dead-route handlers."""
    for path in APP.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if path == MAIN_FILE:
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name not in dead_handlers:
                    for inner in ast.walk(node):
                        if isinstance(inner, ast.Call):
                            func = inner.func
                            called_name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
                            if called_name == name:
                                return True
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                called_name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
                if called_name == name:
                    return True
    return False


class TestEveryGateIsReachable(unittest.TestCase):
    def test_no_gate_function_is_defined_without_a_caller(self) -> None:
        """The guard that would have caught T-6.14, and T-8.18/T-7.8
        before them."""
        gates = _gate_function_names()
        called = _called_names_in_app()
        unreachable = sorted(g for g in gates if g not in called)
        unexplained = [g for g in unreachable if g not in GATE_EXEMPTIONS]
        self.assertEqual(
            unexplained,
            [],
            "Gate function(s) defined but never called from app/: "
            f"{unexplained}. A gate nothing calls is not enforcement. Either "
            "wire it at the chokepoint it protects, or add it to "
            "GATE_EXEMPTIONS with a written reason.",
        )

    def test_exemptions_do_not_outlive_their_reason(self) -> None:
        """An exemption for a gate that has since been wired is stale
        bookkeeping, and stale bookkeeping is how an allowlist rots
        into a permanent blind spot."""
        called = _called_names_in_app()
        wired_but_still_exempt = sorted(g for g in GATE_EXEMPTIONS if g in called)
        self.assertEqual(
            wired_but_still_exempt,
            [],
            f"These gates are now called from app/ but are still listed as "
            f"exempt: {wired_but_still_exempt}. Remove them from "
            "GATE_EXEMPTIONS.",
        )

    def test_exemptions_refer_to_gates_that_exist(self) -> None:
        """Catches a rename that leaves the allowlist pointing at
        nothing, which silently exempts a gate that no longer has that
        name."""
        gates = _gate_function_names()
        phantom = sorted(g for g in GATE_EXEMPTIONS if g not in gates)
        self.assertEqual(phantom, [], f"GATE_EXEMPTIONS names no-longer-existing gates: {phantom}")

    def test_every_exemption_states_a_reason(self) -> None:
        for name, reason in GATE_EXEMPTIONS.items():
            self.assertGreater(
                len(reason.strip()), 40,
                f"Exemption for {name} needs a real explanation, not a placeholder.",
            )


# ---------------------------------------------------------------------------
# HTTP routes
# ---------------------------------------------------------------------------

# Routes the browser is not expected to call. Same rule: a reason, or
# it fails.
ROUTE_EXEMPTIONS = {
    "/": "Serves index.html itself; the browser navigates to it rather than fetching it.",
    "/config": "Fetched with a bare fetch() at boot, before Clerk loads, not through apiFetch.",
    "/health": "Infrastructure probe (Render), never called by the frontend.",
    "/debug/tools": (
        "Introspection endpoint, authenticated and additionally 404'd unless "
        "IRIS_ENABLE_DOCS is set. Enumerates the whole enforcement architecture; "
        "no ordinary user needs it and the frontend correctly never asks."
    ),
    "/advance-phase": (
        "DEAD ROUTE, known and accepted for now. The frontend never advances phase, "
        "which is why every session sits in STARTING_POINT and why the gates hanging "
        "off it (T-5.1, T-5.2) are inert. Fixing this is a phase-machine design "
        "question, not a wiring one; tracked separately."
    ),
    "/deliver": (
        "DEAD ROUTE. Its gates (T-8.18, T-7.8) were moved to the render chokepoint "
        "on 2026-07-27 precisely because nothing called this. The route remains for "
        "API completeness; delivery enforcement no longer depends on it."
    ),
}

_ROUTE_DECORATOR = re.compile(r'@app\.(get|post|put|delete|patch)\(\s*"([^"]+)"')


def _declared_routes() -> set:
    return {m.group(2) for m in _ROUTE_DECORATOR.finditer(MAIN_FILE.read_text(encoding="utf-8"))}


def _exemption_for(route: str):
    """Exemptions are keyed by the distinctive part of a route, not the
    whole path, so "/deliver" covers "/sessions/{session_id}/deliver"
    without the key having to repeat the path parameters."""
    for key, reason in ROUTE_EXEMPTIONS.items():
        if route == key or route.endswith(key):
            return reason
    return None


def _route_tail(path: str) -> str:
    """The last static segment of a route, which is what actually shows
    up in the frontend's string-built URLs.

    static/app.js composes paths like "/sessions/" + id + "/chat", so a
    whole-path match would never hit. The distinctive tail does."""
    segments = [s for s in path.split("/") if s and not s.startswith("{")]
    return segments[-1] if segments else "/"


class TestEveryRouteHasACaller(unittest.TestCase):
    """The guard that would have caught the phase machine being inert.

    /advance-phase and /deliver were both fully implemented, gated, and
    tested by POSTing them directly, while the product never called
    either. Their tests passed for months describing behavior no user
    could reach."""

    def test_no_route_is_served_without_a_frontend_caller(self) -> None:
        frontend = APP_JS.read_text(encoding="utf-8")
        orphans = []
        for route in sorted(_declared_routes()):
            if _exemption_for(route) is not None:
                continue
            tail = _route_tail(route)
            # Matched WITH the leading slash. A bare substring match is
            # far too loose: the tail of /sessions/{id}/chat is "chat",
            # which occurs in ordinary prose in this file's comments, so
            # the guard scored a disconnected route as reachable when
            # tested against a deliberately broken app.js.
            if tail == "/" or ("/" + tail) in frontend:
                continue
            orphans.append(route)
        self.assertEqual(
            orphans,
            [],
            f"Route(s) declared in main.py that static/app.js never calls: "
            f"{orphans}. A route the product cannot reach is not a feature, and "
            "the enforcement behind it is not enforcement. Wire it, or add it "
            "to ROUTE_EXEMPTIONS with a reason.",
        )

    def test_route_exemptions_refer_to_real_routes(self) -> None:
        """A stale exemption is a permanent blind spot: it silently
        excuses whatever route later happens to match that suffix."""
        declared = _declared_routes()
        phantom = sorted(
            key for key in ROUTE_EXEMPTIONS
            if not any(d == key or d.endswith(key) for d in declared)
        )
        self.assertEqual(phantom, [], f"ROUTE_EXEMPTIONS names routes that do not exist: {phantom}")

    def test_every_route_exemption_states_a_reason(self) -> None:
        for route, reason in ROUTE_EXEMPTIONS.items():
            self.assertGreater(
                len(reason.strip()), 40,
                f"Exemption for {route} needs a real explanation, not a placeholder.",
            )


# ---------------------------------------------------------------------------
# Frontend functions
# ---------------------------------------------------------------------------

# Functions reached from somewhere this guard cannot see (an inline
# handler in index.html, or the module's own load listener).
JS_EXEMPTIONS = {
    "showBootError": "Called from the window load listener's catch block, which this guard reads as a reference anyway; listed for clarity.",
    "handleAuthStateChange": "Registered as a Clerk listener callback, not called by name from ordinary code.",
}

_JS_FUNCTION = re.compile(r"^\s*(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(", re.MULTILINE)
_JS_LINE_COMMENT = re.compile(r"//[^\n]*")
_JS_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def _js_without_comments() -> str:
    """Comments stripped before counting references.

    bootstrapSession, the function whose absence lost a live session on
    2026-07-28, appeared exactly twice in app.js: its own declaration
    and one mention in a comment describing the behavior it was
    supposed to provide. A naive reference count would have called that
    reachable."""
    source = APP_JS.read_text(encoding="utf-8")
    source = _JS_BLOCK_COMMENT.sub("", source)
    return _JS_LINE_COMMENT.sub("", source)


class TestEveryFrontendFunctionIsReachable(unittest.TestCase):
    """The guard that would have caught bootstrapSession().

    It was defined, described in a comment as handling session resume
    at page load, and called by nothing. A reload therefore abandoned a
    live session for as long as that code existed."""

    def test_no_frontend_function_is_defined_without_a_reference(self) -> None:
        stripped = _js_without_comments()
        html = (pathlib.Path("static") / "index.html").read_text(encoding="utf-8")
        orphans = []
        for name in sorted(set(_JS_FUNCTION.findall(stripped))):
            if name in JS_EXEMPTIONS:
                continue
            # One occurrence is the declaration itself. Anything
            # reachable is named at least twice: declared, then called
            # or passed as a handler.
            if stripped.count(name) > 1 or name in html:
                continue
            orphans.append(name)
        self.assertEqual(
            orphans,
            [],
            f"Function(s) declared in static/app.js that nothing references: "
            f"{orphans}. This is how a page reload silently abandoned a live "
            "session for as long as bootstrapSession() existed unused. Wire it, "
            "delete it, or add it to JS_EXEMPTIONS with a reason.",
        )

    def test_js_exemptions_refer_to_functions_that_exist(self) -> None:
        declared = set(_JS_FUNCTION.findall(_js_without_comments()))
        phantom = sorted(n for n in JS_EXEMPTIONS if n not in declared)
        self.assertEqual(phantom, [], f"JS_EXEMPTIONS names functions that do not exist: {phantom}")


if __name__ == "__main__":
    unittest.main()
