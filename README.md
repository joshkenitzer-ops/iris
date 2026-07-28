# Iris

Job seeker pipeline. Takes a user from raw career history to a tailored, verified, ATS-compliant resume and cover letter pair, in one guided flow.

Part of the [Lore](https://github.com/joshkenitzer-ops) tool suite. Accent color Amber `#B8860B`.

Formerly Hermes. Renamed 2026-07-21 after a naming collision with commercial "Hermes AI" agent products. References to Hermes persist in git history and in the archived spec line; they refer to this project.

---

## Status

**Live, in private beta.** Deployed to Render as `iris-harness`, behind Clerk authentication, in front of a small group of trusted testers since 2026-07-27.

Nine-phase pipeline working end to end: upload or start from scratch, adversarial audit, foundational resume build, fit check against a job description, tailoring, paired cover letter, three-tier final review, docx delivery. Observed timings on a full-size real resume: audit ~1 minute, foundational build ~3 minutes, fit check under a minute.

681 tests passing. Not yet public, and not yet on production Clerk keys.

## What this repository holds

Iris is built as an **agentic harness**, not a traditional application. There is no pipeline of services calling a model at fixed points. There is a specification that functions as pinned context, a set of deterministic tools the model must invoke, and a model operating under both.

That makes the spec the source of truth rather than documentation. It is versioned, diffed, and reviewed like any other source file.

| Path | Purpose |
| --- | --- |
| `docs/iris-spec.md` | The rules. Two tiers: a stable Constitution and an appendable Decision Log. |
| `docs/iris-tool-list.md` | The enforcement inventory. Every item classified by how it is enforced. |
| `app/` | The harness. FastAPI routes, the tool registry, gates, session state. |
| `app/tools/` | The deterministic checks themselves, one module per pipeline area. |
| `static/` | Single-page frontend, served same-origin. |
| `app/usage.py` | Per-turn token and cost accounting. Attribution reads the tool list, not `Phase`. |
| `tests/` | 57 files. Includes the reachability guard, see Testing below. |

Read the spec first. Read the tool list when you need to know how a rule is enforced.

## The two-tier structure

**Part I, Constitution.** Core rules. Changes rarely. Every change requires the owner's explicit sign-off.

**Part II, Decision Log.** Specific calls, dated, appended freely. Periodically consolidated upward into Part I.

The split exists so that settled rules and in-flight decisions do not compete for the same space. A new call lands in Part II the moment it is made. Promotion into Part I is a separate, deliberate act.

## Amendment protocol

Binding on the development harness and on any model editing the spec. It does not bind Iris itself, which operates under the spec at runtime and has no authority to amend it.

1. A decision that changes a rule is written into the spec in the same turn it is made. Narrating a change without writing it is an incomplete turn.
2. The model drafts the amendment as a diff and shows it. It never edits the spec silently.
3. The diff is committed only after explicit confirmation from the owner.
4. New calls append to Part II. Promotion into Part I is deliberate.
5. Threshold values tuned against real documents live in code config, not in the spec. Tuning must not require an amendment.

Rule 5 matters more than it looks. Anything empirical (extraction confidence thresholds, banned-term frequency limits, context and memory ceilings) belongs in `app/config.py`, or every tuning pass becomes a constitutional amendment.

## Enforcement model

Every capability is classified by how it is enforced. The classification is the point: it decides what code must do and what the model is trusted with.

| Kind | Definition | Registered |
| --- | --- | --- |
| `TOOL` | Deterministic code the model must invoke. The model never performs this by reading. | 72 |
| `GATE` | Deterministic blocker. Delivery or phase advance cannot proceed while it fails. | 11 |
| `HYBRID` | Tool nominates candidates cheaply, model adjudicates. Recall from code, precision from judgment. | 15 |
| `JUDGMENT` | Constitution-guided model judgment with a dedicated critic. Never a single generation pass. | not registered |
| `HUMAN` | Escalates to the user. The model may recommend, never decides. | not registered |

98 items are registered in code. `JUDGMENT` and `HUMAN` are real classifications in the enforcement model but have no deterministic handler to register, by definition; they are described in the spec and carried out by the model under it.

`tests/test_spec_sync.py` fails if a tool registered in code disagrees with the tool list about its own enforcement kind. That guard exists because splitting rules from enforcement created a drift surface the spec itself names as a risk.

Four rules govern the classification. The load-bearing one: **a model asserting compliance, without an underlying deterministic scan, never clears a Critical or Pedantic finding.** A model cannot count pages, cannot reliably detect an altered figure, and cannot be trusted to have checked something it says it checked.

## Testing

```bash
python -m pytest -q
```

One test costs money and needs a network (`test_claude_client_smoke.py`); it skips automatically unless `ANTHROPIC_API_KEY` is set.

**Enforcement is tested through `registry.dispatch`, the path a real model tool call takes, not by calling gate functions directly.** This is a standard rather than a style preference. A production readiness review on 2026-07-27 found the delivery gates correct, fully unit-tested, and *never called by anything*: the tests invoked the route directly, so they proved the function worked while the product shipped ungated. Tests for enforcement now assert reachability, because a test that calls the gate directly is exactly the kind that passed while the gate was dead.

### The reachability guard

`tests/test_reachability_guard.py` fails the build when a check has no caller. It exists because that standard was followed by hand and still missed five separate cases: the delivery gates, the download route, the page-length checks, the unresolved-marker gate, and `bootstrapSession()` in `app.js`. Every one was correct code, unit-tested, and unreachable, and every one was found by a person noticing after it shipped.

Three rules: every `require_*` gate must be called from `app/`; every route in `main.py` must be called from `static/app.js`; every function declared in `app.js` must be referenced.

Two details are load-bearing and should not be "simplified" away:

- **A call site inside a dead-route handler does not count as reachability.** The first version of the guard passed with the delivery gates removed from the render path, because they are still called from `/deliver`, and `/deliver` is a route the product never invokes. It had a blind spot at the exact incident that motivated it.
- **AST for Python, comment-stripping for JavaScript.** `require_turn_completion` is named in a comment in `gates.py` and called by nothing; `bootstrapSession` appeared exactly twice, its declaration and a comment describing behavior it never delivered. A text search scores both reachable.

Exemptions are allowed and must carry a written reason. They are themselves guarded: an exemption for something since wired fails, and an exemption naming something that no longer exists fails. An allowlist that rots silently is a permanent blind spot rather than a record of a decision.

## Running locally

Requires `ANTHROPIC_API_KEY`, `CLERK_ISSUER`, and `CLERK_PUBLISHABLE_KEY`. See `SETUP.md`.

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The app refuses to boot if a required Clerk value is missing, deliberately: a missing key used to surface as a silently broken sign-in form in the browser, which is a far worse way to find out.

## Deployment

Render, single always-on instance, `render.yaml`. `autoDeploy` is **off on purpose**: session state is in memory, so an automatic deploy would drop every in-flight session. Deploys are manual and deliberate.

The in-memory session store is a known, accepted V1 limitation, not an oversight. V2 replaces it with account-based storage behind the same interface.

## Citation convention

Tool-list items carry a `T-` prefix and are cited inline as `(T-3.1)`.

Bare decimal numbers in the spec are its own section numbers and never refer to the tool list. The prefix exists because the two schemes otherwise collide: spec section 5.9 and tool item 5.9 are unrelated rules. Never cite a bare number across files.

## Terminology

The document a user builds once and tailors many times is the **foundational resume**. It was called the "master resume" until 2026-07-28, when a beta tester flagged the term as carrying negative connotations. The rename went through code, filenames, tool names, and prose together rather than UI text alone, so nothing in the codebase should say "master" today.

## Contributing

**Before changing a rule.** Read the Decision Log first. Several rules have been reversed deliberately, with the original reasoning preserved rather than deleted. A rule that looks wrong may have been argued already.

**When changing a rule.** Follow the amendment protocol. Update the tool list in the same commit if enforcement changes; the two files drifting apart is the failure mode this structure was built to prevent, and `test_spec_sync.py` will catch you.

**When adding a rule.** State how it is enforced, along with what it requires. A rule with no enforcement path is a preference.

**When adding a check.** Wire it to something. The most expensive defects found in this codebase were not wrong logic; they were correct logic nothing ever called.

**Self-checks.** The spec is held to its own language standards by convention: no em dashes, no banned vocabulary. Run those checks against the spec itself before committing.

## Related

- `lore` repository: brand tokens (`lore-tokens.css`), three-tier token architecture, `MANIFESTO.md`
- `janus` repository: persistent context and session handoff
- `cassandra` repository: adversarial review
- `hermes` repository: deprecated. Original application architecture, kept for history.

Iris calls none of them at runtime. It is standalone by design principle, not by accident of scheduling.
