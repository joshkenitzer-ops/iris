# Iris

Job seeker pipeline. Takes a user from raw career history to a tailored, verified, ATS-compliant resume and cover letter pair, in one guided flow.

Part of the [Lore](https://github.com/joshkenitzer-ops) tool suite. Accent color Amber `#B8860B`.

Formerly Hermes. Renamed 2026-07-21 after a naming collision with commercial "Hermes AI" agent products. References to Hermes persist in git history and in the archived spec line; they refer to this project.

---

## What this repository holds

Iris is being built as an **agentic harness**, not a traditional application. There is no pipeline of services calling a model at fixed points. There is a specification that functions as pinned context, a set of deterministic tools the model must invoke, and a model operating under both.

That makes the spec load-bearing code rather than documentation. It is versioned, diffed, and reviewed like any other source file.

| File | Purpose |
| --- | --- |
| `iris-spec.md` | The rules. Two tiers: a stable Constitution and an appendable Decision Log. |
| `iris-tool-list.md` | The enforcement inventory. 142 items, each classified by how it is enforced. |

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

Rule 5 matters more than it looks. Anything empirical (extraction confidence thresholds, banned-term frequency limits) belongs in config, or every tuning pass becomes a constitutional amendment.

## Enforcement model

Every capability is classified by how it is enforced. The classification is the point: it decides what code must do and what the model is trusted with.

| Kind | Definition | Count |
| --- | --- | --- |
| `TOOL` | Deterministic code the model must invoke. The model never performs this by reading. | 76 |
| `GATE` | Deterministic blocker. Delivery or phase advance cannot proceed while it fails. | 20 |
| `HYBRID` | Tool nominates candidates cheaply, model adjudicates. Recall from code, precision from judgment. | 15 |
| `JUDGMENT` | Constitution-guided model judgment with a dedicated critic. Never a single generation pass. | 36 |
| `HUMAN` | Escalates to the user. The model may recommend, never decides. | 6 |

Counts overlap: some items carry two kinds.

Four rules govern the classification. The load-bearing one: **a model asserting compliance, without an underlying deterministic scan, never clears a Critical or Pedantic finding.** A model cannot count pages, cannot reliably detect an altered figure, and cannot be trusted to have checked something it says it checked.

## Citation convention

Tool-list items carry a `T-` prefix and are cited inline as `(T-3.1)`.

Bare decimal numbers in the spec are its own section numbers and never refer to the tool list. The prefix exists because the two schemes otherwise collide: spec section 5.9 and tool item 5.9 are unrelated rules. Never cite a bare number across files.

## Contributing

**Before changing a rule.** Read the Decision Log first. Several rules have been reversed deliberately, with the original reasoning preserved rather than deleted. A rule that looks wrong may have been argued already.

**When changing a rule.** Follow the amendment protocol. Update the tool list in the same commit if enforcement changes; the two files drifting apart is the failure mode this structure was built to prevent.

**When adding a rule.** State how it is enforced, along with what it requires. A rule with no enforcement path is a preference.

**Self-checks.** The spec is held to its own language standards by convention: no em dashes, no banned vocabulary. Run those checks against the spec itself before committing.

## Related

- `lore` repository: brand tokens (`lore-tokens.css`), three-tier token architecture, `MANIFESTO.md`
- `janus` repository: persistent context and session handoff
- `cassandra` repository: adversarial review
- `hermes` repository: deprecated. Original application architecture, kept for history.

Iris calls none of them at runtime. It is standalone by design principle, not by accident of scheduling.

## Status

Spec complete as of 2026-07-24. 19 EARS requirements, all buildable. One open item, non-blocking: read the locked Lore palette tokens before UI work.

Not yet built.
