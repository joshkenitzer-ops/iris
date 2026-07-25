# Iris Harness: Pre-Deploy Engineering Review

Date: 2026-07-25
Scope: `app/`, `tests/`, `render.yaml`, `requirements.txt`
Context: first deployment to a public host, small trusted user group, single always-on instance

The enforcement architecture is the strong part of this codebase. The registry/gate split is
well-reasoned, the "gates run server-side regardless of model self-report" principle is real and
implemented, `test_spec_sync.py` closing the cross-file drift risk is good engineering,
and the test suite is thorough for the pure-logic layer. The findings below are concentrated in the
edges that only start to matter when this stops being a single-user local process: the HTTP trust
boundary, resource lifecycle, and dependency reproducibility.

---

## Blockers: fix before this is reachable from the internet

### B1. The client supplies the conversation history

`POST /sessions/{id}/chat` accepts `history: List[Dict[str, Any]]` from the request body and
forwards it verbatim to the model:

```python
messages = body.history + [{"role": "user", "content": body.message}]
```

The client is therefore free to author the entire prior conversation, including assistant turns and
`tool_result` blocks. A user can hand the model a transcript in which every check already ran and
passed, then ask it to proceed.

This directly contradicts the premise the rest of the architecture is built on. `enforcement.py`'s
docstring states the point plainly: a model asserting compliance without an underlying
deterministic scan is never sufficient. But a forged `tool_result` in client-supplied history is
exactly that assertion, arriving in the one channel nothing validates.

The hard gates do hold. `require_no_open_criticals` and friends run against real server-side
session state in `/advance-phase` and `/deliver`, and a forged transcript cannot fabricate a `Fact`
in `session.registry`. So this is not a total bypass. It is, however, a full compromise of the
model-facing enforcement layer, and it means the audit trail of what the model was told is
untrustworthy.

**Fix:** move the transcript to the server. Add `messages: List[Dict[str, Any]]` to `Session`,
append the user turn and the model's response there, and reduce `ChatRequest` to `message` plus
options. The client sends what's new; the server owns the history. This also removes the
round-tripping problem in B2 below.

### B2. Anthropic SDK objects are returned to the client and expected back

`run_turn` appends `response.content` (a list of SDK block objects) into `working_messages`, then
returns that list as `result["messages"]`, which `/chat` returns to the client. The client is then
expected to send it back as `history` next turn.

Two problems compound: those objects are not plain JSON and their serialized shape is an SDK
implementation detail, and this is the mechanism that makes B1 exploitable in the first place.
Fixing B1 by keeping the transcript server-side resolves most of this; whatever is stored should
still be normalized to plain dicts rather than SDK objects, so an SDK upgrade cannot change the
shape of persisted state.

### B3. Dependencies are entirely unpinned

```
fastapi
uvicorn
pydantic
pytest
anthropic
python-docx
pypdf
pyjwt[crypto]
```

Render runs `pip install -r requirements.txt` on every deploy. With no version constraints, a
deploy triggered by an unrelated one-line change can pull a new major version of any of these and
break production, with no corresponding change in your code and nothing in the diff to explain it.

`anthropic` is the sharpest edge: it is pre-1.0 and has a history of breaking changes between minor
versions, and it is the dependency that the entire `/chat` path runs through.

**Fix:** pin with compatible-release constraints (`anthropic~=0.120`, `fastapi~=0.139`, and so on),
or commit a fully frozen `requirements.txt` from a known-good venv and keep looser constraints in a
separate dev file. Also split `pytest` out of the production requirements; it does not belong in
the deployed image.

### B4. Nothing bounds resource use on the endpoint that spends money

`/chat` has no rate limit, no cap on `message` length, no cap on `history` size, and
`max_tool_iterations=12` per call. Every call bills your Anthropic account.

You have already decided to defer billing/usage limits, and that is reasonable as a product
decision. This finding is narrower and I would not defer it: the concern is not fair-usage
accounting between colleagues, it is that a single leaked token, a runaway client retry loop, or an
accidental paste of a very large document creates an unbounded charge with no ceiling and no alert.

**Minimum viable version:** a `max_length` on `ChatRequest.message`, a cap on stored transcript
length, and a per-user request counter in memory. All cheap. A billing alert on the Anthropic
console is worth setting the same day regardless.

### B5. Sessions accumulate forever

`SessionStore` only removes an entry when someone explicitly calls `DELETE /sessions/{id}`. Nothing
expires. In the previous local-only model this was invisible because the process restarted
constantly; on an always-on instance chosen specifically so it never restarts, every abandoned
session is retained for the life of the process.

Each `Session` holds the full JD text, the facts registry, all findings, and (after B1 is fixed) the
transcript. Render's Starter plan gives you 512MB. Users who close the tab without logging out
(which is to say, most users) leak a session each time.

**Fix:** a `last_accessed` timestamp on `Session`, updated in `store.get`, plus a periodic sweep or
lazy eviction of anything past a TTL. An `OrderedDict` with a maximum size is a reasonable cruder
alternative.

---

## Should fix

### S1. The concurrency guarantee is narrower than the docstring claims

`SessionStore`'s docstring says a single lock is enough because "no operation does more than one
dict read-or-write, so there is no check-then-act window." That is true of the dict, and the dict is
not the shared mutable state that matters.

`get()` returns a live reference to a `Session` under the lock and then releases it. Every caller
mutates that object outside any lock: `session.phase = target`, `session.registry[fact_id] = ...`,
appended findings. Two concurrent requests against the same session mutate the same object with no
synchronization. `store.save()` is a no-op in practice, since the object is already in the dict by
reference.

Realistically, one user rarely issues concurrent writes to one session, so the exposure is low. The
problem is that the comment asserts a guarantee the code does not provide, and the next person to
touch this will believe it. Either add a per-session lock, or amend the docstring to state exactly
what is and is not protected.

### S2. `_key` builds a composite string key from two untrusted-ish values

```python
return f"{user_id}:{session_id}"
```

`session_id` comes straight off the URL path and is fully attacker-controlled. If a `user_id` could
ever contain a colon, keys become ambiguous: user `a` requesting session `b:S` produces the same key
as user `a:b` holding session `S`.

Clerk's `sub` values are opaque `user_...` identifiers with no colons, so this is not currently
exploitable. It is a latent boundary bug guarding a security property, and it costs nothing to make
structurally impossible: use `(user_id, session_id)` as a tuple key.

### S3. Error text leaks through the tool loop, contradicting the hardening in `main.py`

Batch 11 added a generic exception handler so nothing internal reaches a client. But
`claude_client.run_turn` does this:

```python
except Exception as exc:
    content = {"error": str(exc)}
```

That raw exception string goes into `tool_results`, into the transcript, and back out to the client
in the returned `messages`. A `ToolNotFoundError`, a path in a docx parse failure, or anything else
raised inside a tool round-trips to the caller. The two error-handling policies should agree: log
the detail, hand the model a generic failure plus the tool name.

### S4. Client-controlled `tool_ids`, and an unknown id returns 500

`ChatRequest.tool_ids` lets the caller choose which tools the model may use. A client can pass a
narrowed list, or `[]`, and suppress the model-facing checks for that turn. Same reasoning as B1:
the server-side gates still hold, but the client should not be steering the enforcement surface.

Separately, `registry.claude_schemas` calls `registry.get(i)`, which raises `ToolNotFoundError` (a
`KeyError`) for an unrecognized id. That escapes as an unhandled exception and becomes a 500. Bad
client input should be a 400. Either drop `tool_ids` from the public request model or validate it
against the registry and reject unknown ids explicitly.

### S5. `run_turn` raises on iteration exhaustion

Hitting `max_tool_iterations` raises `RuntimeError`, which reaches the client as a generic 500 with
no indication of what happened. A tool loop is a plausible runtime condition, not an
impossible-state bug. Return a structured result the caller can act on.

### S6. Long synchronous work in `def` route handlers

`/chat` is a sync handler that blocks on a multi-round-trip Claude conversation, potentially for
minutes. FastAPI runs sync handlers in a bounded threadpool. On one small instance, a handful of
concurrent long chats plus docx and PDF parsing will saturate it, and later requests queue with no
feedback. Worth load-testing with a few simultaneous users before you invite the whole team, and
worth considering `async def` with the async SDK client if it bites.

### S7. `tool_result` content is a Python repr, not JSON

```python
"content": str(content)
```

This produces `{'passed': True, ...}` with single quotes: not valid JSON, and the model has to
recover the structure from a Python-flavored string. `json.dumps(content)` is the same line count
and unambiguous.

---

## Notes and minor items

**N1.** `gates.py`'s module docstring references `app/tools/gates_defs.py`. That file does not
exist. Stale reference, likely from an earlier plan; worth correcting since the docstring is
otherwise load-bearing documentation of the architecture.

**N2.** `session.py`'s module docstring still opens with "This is an in-memory implementation. It is
correct for local development and wrong for production... Before a real deploy, replace
SessionStore's dict with a real per-user store." That advice is correct and is about to be
knowingly ignored. Acceptable for an MVP with a handful of trusted users, provided B5 is addressed,
but it should be a conscious decision recorded somewhere rather than a comment the deploy silently
contradicts. It also means every in-flight session is lost on each deploy, which with `autoDeploy:
true` happens on every push to `main`.

**N3.** `load_spec_text(SPEC_PATH)` re-reads the spec from disk on every single chat request. Read
it once at startup, or cache it.

**N4.** `docs/iris-spec.md` must be committed and present in the deployed tree or `/chat` fails at
runtime with a `FileNotFoundError` and a 500. Nothing verifies this at startup. A startup check that
fails fast beats a 500 on the first user request.

**N5.** `MODEL = "claude-sonnet-5"` is hardcoded in `config.py`. Making it an env var lets you change
models without a redeploy.

**N6.** `app/main.py` has no test coverage at all. The convention of not importing it in tests was
reasonable when it was thin glue, but it now holds the auth dependency, the CORS policy, and the
error handler, all security-relevant. FastAPI's `TestClient` with a dependency override for
`get_current_user_id` would cover the routing and isolation behavior without needing a live Clerk
tenant, the same way `test_clerk_auth.py` handles the crypto offline.

**N7.** `autoDeploy: true` means any push to `main` deploys immediately and drops all sessions.
Consider setting it false and deploying deliberately, at least until there is a staging target.

---

## Suggested order

1. B3 (pin dependencies) and N4 (confirm `docs/` ships) are the two that will bite on the very first
   deploy. Both are minutes of work.
2. B1 plus B2 together, since fixing the transcript ownership resolves both.
3. B5 and B4, the two runtime-resource risks.
4. S1 through S7 as a cleanup batch.
5. N6 last, but before the user count grows.

None of these are reasons not to ship to a small trusted group. B1 and B3 are the two I would not
deploy without.

---

# Addendum: targeted security audit and resolution status

Added after the review above, covering three areas raised specifically:
prompt injection, row-level security (with reference to CVE-2025-48757),
and open debug/admin routes. All fixes below shipped in batch 13.

## A1. Prompt injection

**Vector confirmed.** `ingest_document` (T-0.1) returned raw
`extracted_text` in `ToolResult.data`, which `claude_client` stringified
directly into a `tool_result` block: no delimiting, no provenance
marking, no length cap. Attacker-controlled text arrived in model
context looking exactly like trusted tool output. `ingest_job_description`
(T-6.1) had the same shape.

**Threat model.** A user injecting their own upload is low-value; they
can already type anything into `/chat`. The real vector is third-party
content: a JD copied from a hostile posting, or a performance document
or resume received from someone else. There the document's author is the
attacker and the user is the victim.

**Blast radius, as measured rather than assumed.** Two things injection
cannot reach, both structural and worth preserving:

- Another user's data. `dispatch()` injects only the authenticated
  session, and no registered tool accepts a `user_id` or `session_id`
  argument, so there is no parameter an injected instruction could
  target however persuasively it is phrased.
- `ANTHROPIC_API_KEY`, which never enters model context.

What it could reach: 17 session-scoped tools, 6 of which write.

**The critical finding: T-2.18 could open the delivery gate.**
`apply_dismissed_findings` set `dismissed = True` with no severity
check. `session.py` carried the invariant as a field comment
("Critical is never dismissible") that nothing enforced.
`open_criticals()` filters on `not dismissed`, and
`require_no_open_criticals` (T-8.18, the delivery gate) reads
`open_criticals()`. Reproduced before the fix:

```
open criticals before: 1
DELIVERY GATE: BLOCKED as designed -> T-8.18
  [one call to apply_dismissed_findings]
open criticals after : 0
finding.severity still: Critical | dismissed: True
DELIVERY GATE: OPEN  <-- Critical bypassed
```

A fabrication flag, the exact thing Iris exists to catch, could be
cleared and the package shipped. Reachable by prompt injection, by a
malicious profile import, or by the model taking a shortcut under
pressure to finish. A spec violation independent of the security impact.

**Fixed:**
- `Finding.dismiss()` is now the only supported route to the flag and
  raises `CriticalNotDismissibleError` on a Critical. Enforced on the
  model, not at call sites, because a check in one caller is a check the
  next caller forgets.
- `apply_dismissed_findings` routes through it, refuses Critical
  entries, reports each refusal as a High finding, and continues
  importing the rest rather than discarding a legitimate profile.
- `open_criticals()` keeps its `not dismissed` clause as defense in
  depth, so a `Finding` constructed directly with `dismissed=True`
  (import, future code path, fixture) still cannot go quiet.
- New `app/untrusted_text.py`: all externally-sourced text is fenced in
  named delimiters, labeled with its source, capped at
  `MAX_INGEST_TEXT_CHARS` with truncation stated rather than silent, and
  carries the handling rule inline next to the data. Attempts to forge
  either delimiter are neutralized.

**Deliberately not done:** no blocklist for phrases like "ignore
previous instructions". Those fail on paraphrase, encoding, and
translation, and their real cost is the false confidence they create.
Delimiting plus least privilege is the defense.

**Still open (V2):** nothing enforces that the hidden-text scan
(`check_hidden_text_in_docx`) runs *before* ingested text reaches the
model. The absolute hidden-text ban is already a partial mitigation for
invisible-text injection in docx; making the ordering explicit would
make it a real one.

## A2. Row-level security / CVE-2025-48757

**Not applicable to the current architecture, and worth stating plainly
rather than inventing work.** There is no database: no Supabase, no
Postgres, no anon key, no tables. Session state is a Python dict in
process memory, and the isolation boundary is the `(user_id,
session_id)` keyed lookup in `SessionStore`. There is nothing to write
an RLS policy against.

The concern is correct for V2, when account-based storage lands. The CVE
was an incorrect-authorization issue caused by missing or insufficient
RLS policies on Supabase tables backing Lovable-generated projects.
The specific gap: tables created through raw SQL, a migration, or AI
tooling do not get RLS automatically, unlike ones made in the dashboard
Table Editor. The public anon key ships in every client bundle by
design, so on an unprotected table it stops being a harmless identifier
and becomes a working read/write credential. 170+ production apps were
confirmed exposed.

**The architectural point that matters more than any policy checklist:**
Iris is currently immune to this entire class because the client never
talks to a datastore directly. It goes through FastAPI, which resolves
identity server-side from a verified Clerk token. Keeping that shape in
V2 (client -> API -> DB, never client -> DB) means the CVE's pattern
cannot reproduce. Adopting a direct-client-to-database architecture is
what would introduce it.

**V2 requirements, recorded now so they are not rediscovered later:**
- RLS enabled on every table, verified by an automated test rather than
  by inspection.
- Policies keyed on the authenticated Clerk `sub`, with per-row
  ownership checks.
- Service-role key server-side only, never shipped to a client.
- Verify with a direct anon-key request against the REST endpoint. That
  is how the CVE was found, and it is the only proof that counts.

## A3. Debug and admin routes

`/debug/tools` was already gated in batch 11; route-by-route check
confirmed 7 of 8 routes require auth, with only `/health` open by
design.

**New finding: FastAPI's own docs endpoints were public.**
`FastAPI(title=..., version=..., debug=False)` does not disable them, so
`/docs`, `/redoc`, and `/openapi.json` were all served unauthenticated,
handing any anonymous visitor a complete interactive map of every route,
schema, and field name, plus a precise target list.

**Fixed:** all three are `None` unless `IRIS_ENABLE_DOCS` is set, so they
work locally and are off in production. `/debug/tools` is now gated on
the same flag in addition to requiring auth, since it enumerates the
whole enforcement architecture to any authenticated user. `/health`
stays open and minimal.

## Resolution status of the original review

| Item | Status |
| --- | --- |
| B1 client-supplied history | Fixed. Transcript is server-owned on `Session`; `history` removed from `ChatRequest`. |
| B2 SDK objects in stored state | Fixed. `_blocks_to_plain()` normalizes before persisting. |
| B3 unpinned dependencies | Fixed. Compatible-release pins; `pytest`/`httpx` split into `requirements-dev.txt`. |
| B4 no input caps or rate limit | Fixed. `max_length` on messages, per-user rolling-window limiter on `/chat`, 429 with `Retry-After`. |
| B5 sessions never expire | Fixed. Idle TTL eviction, per-user session quota, `last_accessed` refreshed on read. |
| S1 overstated concurrency guarantee | Fixed. Docstring corrected; per-session locks added and used by `/chat`. |
| S2 string composite key | Fixed. Tuple key. |
| S3 error text leaking to model | Fixed. Logged server-side, generic message to the model. |
| S4 client-controlled `tool_ids` | Partly fixed. Validated against the registry, unknown ids now 400 not 500. Still client-selectable by design; server-side gates remain the enforcement. |
| S5 `RuntimeError` on loop exhaustion | Fixed. `ToolLoopExhausted` -> 409. |
| S6 blocking sync handlers | Not addressed. Load-test before widening access. |
| S7 `str()` instead of JSON | Fixed. `json.dumps`. |
| N1 stale `gates_defs.py` reference | Fixed. |
| N2 session docstring vs reality | Fixed. States the accepted limitation and the eviction requirement. |
| N3 spec re-read per request | Fixed. Cached at startup. |
| N4 missing spec file at runtime | Fixed. Lifespan startup check fails fast. |
| N5 hardcoded model | Fixed. `IRIS_MODEL` env override. |
| N6 no coverage of `main.py` | Not addressed. Needs `TestClient` with a dependency override. |
| N7 `autoDeploy: true` | Fixed. Now `false`. |
