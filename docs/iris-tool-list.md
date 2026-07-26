# Iris Tool List (Phase 1)

Status: settled 2026-07-23. Companion to `iris-spec.md`, which states the rules this inventory enforces.

**ID convention.** Every item carries a `T-` prefix. The spec cites these IDs directly. Without the prefix, spec section numbers and tool IDs share a format and collide: spec 5.9 and tool 5.9 are unrelated rules. Never cite a bare number across files.
Date: 2026-07-23
Sources: Hermes Product Spec v0.4 (July 20, 2026), Lore Active Log 2026-07-23 sections 1.2, 1.3, 3.

---

## 0. Orientation

**v0.4 already contains the answer to Phase 1's central question.** Two of its Design Principles state the code/judgment boundary directly:

> Programmatic verification: Quality checks that can be expressed in code, word counts, banned terms, character-level formatting, are checked in code, not inferred from model output.

and Phase 8:

> Every check in this phase is run programmatically wherever the check can be expressed in code. Model judgment is used only where a check cannot be reduced to a deterministic rule. A model asserting compliance, without an underlying deterministic scan, is not sufficient to clear a Critical or Pedantic severity item.

This exercise is not inventing that boundary. It is applying it item by item, which v0.4 never does. Both statements were carried into the spec's Constitution tier on 2026-07-23 (Design Principle 9 and section 4); they are the load-bearing rule the rest of this inventory derives from.

**The EARS table is already a gate list.** Nineteen requirements, fourteen from v0.9 plus five added 2026-07-24, most of them deterministic enforcement. Section 12 below maps each to the tool that enforces it. All fourteen are buildable as of 2026-07-23.

**Scope decision, 2026-07-23.** Iris is a product for other job seekers, per v0.4's Design Principles and Scope Boundary. Rules specific to any one user's record are not spec rules. The spec holds mechanisms; user data holds content.

**V1 scope amendments, 2026-07-23.** Authentication moves into V1; account-based storage stays V2. Identity without content. This splits v0.4's Scope Boundary row "Account-based storage, server-side Master Resume persistence", which currently bundles the two, and it retires `dangerouslyAllowBrowser`, since auth forces a server and the API key moves off the client. No PII is persisted in V1. User state travels in a portable Iris Profile file the user holds.

**Service boundaries are not tracked here, by decision of 2026-07-24.** The six services were an artifact of the app architecture. This inventory is organized by phase and captures their functionality in full; nothing in the spec depends on the old boundaries. `buildService`, `tailorService`, `docxService`, and `reviewService` survive only as names in v0.9 and the handoff.

---

## 1. Verdict key

| Verdict | Meaning |
| --- | --- |
| **TOOL** | Deterministic code the model must invoke. The model never performs this by reading. |
| **GATE** | Deterministic blocker. Delivery or phase advance cannot proceed while it fails. Subtype of TOOL, separated because it changes harness control flow rather than producing a finding. |
| **HYBRID** | Tool nominates candidates cheaply, model adjudicates each one. Recall from code, precision from judgment. |
| **JUDGMENT** | Constitution-guided model judgment with a dedicated second-pass critic. Never a single generation pass. |
| **HUMAN** | Escalates to you. Model may recommend, never decides. |

---

## 2. Phase 0: Starting Point

| # | Item | Verdict | Reasoning |
| --- | --- | --- | --- |
| T-0.1 | Ingest docx/PDF, extract text | TOOL | Parsing is solved. Model tokens spent here are waste. |
| T-0.2 | Extraction confidence scoring | HYBRID | Composite, fail-closed, evaluated per section. Routes to manual review if any signal trips: no text layer and OCR mean confidence under 85%; replacement or control characters above 2% of extracted characters; fewer than two role blocks with a parseable date range; over 20% of date-like strings failing to parse. Threshold values are code config, not spec content, so tuning does not require a spec amendment. Whether partial content is still usable remains judgment. |
| T-0.3 | Route to manual review on low confidence | GATE | EARS requirement. Enforcement must not be prose the model may skip when the content looks readable enough. |
| T-0.4 | Colleague-name replacement with generic labels | HYBRID + GATE | Name detection needs reading; regex misses initials and unusual names. Model flags, tool performs the substitution so the edit is auditable, gate blocks storage until clean. Note the July 21 precedent is stricter than v0.4: peer and manager feedback was excluded from the resume and from memory entirely, not name-scrubbed. Section-level exclusion is TOOL when sections are labeled. Needs your call on which rule is real. |
| T-0.5 | Organize inventory by role and time period | JUDGMENT | Assigning material to a role is judgment. The EXPERIENCE-versus-PROJECTS split is not, as of 2026-07-24: work inside the scope of employment is an EXPERIENCE bullet, work outside it is a PROJECTS entry. |
| T-0.6 | careerInventory schema validation | TOOL | No fixed section count. Two flags per section, inventory-required and output-required, evaluated separately. Relative order is locked. Empty optional sections are omitted from output rather than rendered as an empty heading. CONTACT is four pipe-delimited fields with field-level flags: email, phone, and location non-empty, LinkedIn optional. Blank-but-present governs rendering, not satisfaction of a required flag. Dispositions settled 2026-07-24; see the spec's Phase 2 table. |
| T-0.7 | Structured intake form | TOOL | Form. No model. |
| T-0.8 | Near-duplicate collapse in bulk sources | HYBRID | Not in v0.4, but the 338-page export re-listed cumulative history per review cycle. Similarity clustering is cheap code; choosing the canonical version of a repeated claim is judgment, since a later instance can be a revision rather than a copy. |
| T-0.9 | Primary-source verification of an existing claim | HYBRID + HUMAN | Not in v0.4. Full-text search of a source for a claim's distinctive tokens is a tool, and it is what caught the Large Customer Sales fabrication. Interpreting absence is judgment, and per the July 21 standing note the model does not resolve it: absence means treat as suspect and ask. |

## 3. Phase 1: Audit

| # | Item | Verdict | Reasoning |
| --- | --- | --- | --- |
| T-1.1 | Content gaps | JUDGMENT | Requires knowing what a strong record for this career shape looks like. Not enumerable. |
| T-1.2 | AI slop dimension | delegates to Phase 3 | Same engine, different entry point. No separate implementation. |
| T-1.3 | Voice | JUDGMENT | "Reads like a specific person who did specific work" has no mechanical proxy. |
| T-1.4 | Formatting dimension | delegates to Phase 4 | Same. |
| T-1.5 | Structure (strongest work leads, arc visible, roles connect) | JUDGMENT | Ordering quality is comparative and contextual. |
| T-1.6 | Severity categorization | JUDGMENT | Applies the spec's severity table to a specific finding. Bounded judgment. |
| T-1.7 | Findings carry-forward checklist | TOOL | State. Dismissal keyed by content signature, per existing convention. |
| T-1.8 | Audit Critical disposition | GATE | Phase 2 cannot begin while a Phase 1 Critical is undispositioned. Fixed or acknowledged-with-reason both satisfy it. Acknowledgment is recorded and the finding resurfaces at Final Review under T-8.18, where acknowledgment is not offered. |

## 4. Phase 2: Master Build and Locked Facts Registry

| # | Item | Verdict | Reasoning |
| --- | --- | --- | --- |
| T-2.1 | Bullet drafting | JUDGMENT | Generation. |
| T-2.2 | Bold-lead structural check (bold run present, 3-6 words) | TOOL | Countable in the docx XML. Binary. |
| T-2.3 | Bold-lead quality (label earns its body) | JUDGMENT | Decided 2026-07-23: this check runs at Master Build, not only at Final Review. Same critic as T-8.4. v0.4 places it in Phase 8 alone, which allows a hollow label to propagate into every tailored copy before anything catches it. Catching it once at the source is the July failure pattern (b) fix. |
| T-2.4 | Role summary length (1-2 sentences) | TOOL | Count. |
| T-2.5 | Role summary content | JUDGMENT | Generation. |
| T-2.6 | HEADLINE composition | JUDGMENT | Choosing the strongest three to four hard skills is a ranking call. |
| T-2.7 | HEADLINE skill-backing check | TOOL | v0.4: every skill listed must already exist in the Locked Facts Registry. This is set membership. Fully mechanical, and it is the cheapest anti-fabrication check in the entire spec. |
| T-2.8 | HEADLINE placement (after Name, before Contact) | TOOL | Position check. |
| T-2.9 | Fact extraction from approved prose into discrete registry entries | HYBRID | Typing, storage, and indexing are code. Deciding where one assertion ends and the next begins is judgment, bounded by the granularity rule: a fact is the smallest independently verifiable assertion. See section 16. |
| T-2.9a | Value immutability enforcement | GATE | `value` is write-once. A correction retires the fact and writes a successor rather than editing in place, preserving the audit trail for anything already shipped. |
| T-2.9b | Variant approval | HUMAN | An alternate phrasing of an existing fact requires user approval before the value-match tool will accept it. Without this the model can widen its own constraints. |
| T-2.10 | Fact locking on section approval | TOOL | EARS event-driven. Approval fires the write. |
| T-2.11 | Internal project name detection | TOOL | Match against the user's own custom term list (T-3.4). No global codename registry exists in a multi-user product. |
| T-2.12 | Whether a non-registry proper noun needs a plain descriptor | JUDGMENT | Unknown names are not enumerable. |
| T-2.13 | Audit-finding prompts during build | TOOL | State surfacing. |
| T-2.14 | Iris Profile export | TOOL | Single downloadable markdown file, internally sectioned: Locked Facts Registry, custom term lists, preferences, dismissed findings, package state. Package state carries version counters and submitted status per company and role, which is what makes T-4.13 versioning and T-9.8 locking possible without server storage. One artifact rather than several, since the user already carries the master docx separately and v0.4 forbids storing anything in it. Substitutes for storage: the user keeps their own state, so V1 has no deletion obligation and no retention policy. |
| T-2.15 | Iris Profile import and schema validation | TOOL | Re-upload at session start. Validates structure and version before any fact enters context. A malformed profile fails loudly rather than half-loading. |
| T-2.16 | Profile integrity check | TOOL | Checksum on export, verified on import. Guards against truncation and corruption, not user editing. The registry constrains the model, not the user, who owns the facts and can already state a wrong number in Phase 2. |
| T-2.17 | Registry rehydration from an uploaded master | TOOL | Fallback path when no profile file exists. First session, or a user who lost theirs. |
| T-2.19 | Profile-to-master fingerprint binding | TOOL | The profile stores a fingerprint of the master it was built from. A mismatch on import warns, records to the session log, and proceeds. Distinct from T-2.16, which checks the profile against corruption rather than against the document it describes. |
| T-2.18 | Dismissed-finding persistence | TOOL | Dismissals travel in the profile, keyed by content signature per existing convention. Revised text yields a new signature and the finding correctly returns. Critical findings are excluded: v0.4 blocks delivery on any open Critical, so they are not dismissible, and a persisted dismissal must never carry one past the gate in a later session. |

## 5. Phase 3: Slop Audit

Everything here runs on every draft and revision. Anything JUDGMENT in this section is paid for repeatedly, which is why the nominating tools matter more here than anywhere else.

| # | Item | Verdict | Reasoning |
| --- | --- | --- | --- |
| T-3.1 | Em dashes | GATE | EARS ubiquitous. One character class, absolute. The canonical case for never invoking a model. |
| T-3.2 | Hidden text (invisible, white-on-white, concealed) | GATE | EARS ubiquitous. Positive visibility verification: every text run in the output must be demonstrably visible when rendered, and anything that cannot be shown visible fails. An absolute ban cannot be backed by a blocklist, so the known-pattern list (font color against background, hidden run attribute, zero-size fonts) is retained only as a fast pre-filter. Safety-critical: concealed text is a prompt-injection vector into any downstream parser. Never configurable. |
| T-3.3 | Banned vocabulary, default list | TOOL | Lemma-aware match, two tiers. Always-flagged terms fire on any occurrence. Frequency-gated terms ("effectively", "directly") fire above a per-document occurrence threshold held in code config. Needs a scoped exception path for quoted JD text and company names; exceptions escalate rather than resolving in-model. |
| T-3.3a | Banned-term misuse assessment | HYBRID | For frequency-gated terms below the threshold: whether the use is imprecise where more direct language would serve. The counter nominates every occurrence cheaply; judgment rules on each. Separated from T-3.3 because a frequency counter cannot assess precision, and a hard ban on ordinary English produces false positives on every draft. |
| T-3.4 | User-defined banned terms | TOOL | Same engine, second list. No separate design. |
| T-3.5 | Vague metrics ("significantly improved") | TOOL | Quantifier lexicon plus absence of an adjacent numeral. Higher precision than it looks, and it fires constantly. |
| T-3.6 | Uniform sentence cadence | TOOL | Variance of sentence length and structure across a run is a computed statistic. This is a strong TOOL call that reads like judgment. |
| T-3.7 | Colon-then-gerund | TOOL | High-precision syntactic pattern. |
| T-3.8 | Numerals not spelled out (v0.5) | TOOL | Regex. Also the outstanding Sequence 1 bug, which is evidence it should never have depended on a model. |
| T-3.9 | "Not just X but Y" | HYBRID | Literal form is a regex; paraphrased variants are not. Tool catches the cheap majority, model sweeps the rest. |
| T-3.10 | Triple parallel noun phrases | HYBRID | "X, Y, and Z" is trivially detectable. Whether it reads as slop or as accurate enumeration is judgment. |
| T-3.11 | Passive weak endings and passive hedges (v0.6) | HYBRID | POS tagging finds passive constructions deterministically. Whether the passive weakens the claim is judgment. |
| T-3.12 | Parallel pair endings, fragment triplets | HYBRID | Structural repetition is measurable. Rhetorical intent is not. |
| T-3.13 | Run-on sentences (v0.9) | HYBRID | Length, clause count, and conjunction count nominate. Whether it is two ideas or one long one is judgment. |
| T-3.14 | Self-annotation | JUDGMENT | A sentence explaining why a bullet is impressive has no surface marker. Pure reading. |
| T-3.15 | Custom term leak blocker | GATE | Same engine as T-3.4, escalated to a gate. A user's employer-confidential names must never reach output. Exact match against the per-user list, with a per-user allowlist for public exceptions. Never judgment. |
| T-3.16 | Plain-English explainer on first use (v0.9) | HYBRID | Registry members are tool-detectable. Whether a non-registry proper noun needs an explainer is judgment. Failure pattern (a) applies: the explainer itself can introduce an unsupported claim, so its output routes back through T-8.3. |

## 6. Phase 4: Formatting

| # | Item | Verdict | Reasoning |
| --- | --- | --- | --- |
| T-4.1 | No tables or multi-column layouts | TOOL | XML inspection. |
| T-4.2 | No graphics, icons, special characters in headings | TOOL | XML inspection. |
| T-4.3 | Contact in body, not header or footer | TOOL | XML inspection. |
| T-4.4 | Font family and size (v0.6: five allowed families, 10-12pt body, 11-14pt name) | TOOL | Inspectable. |
| T-4.5 | Date format Mon YYYY - Mon YYYY | TOOL | EARS ubiquitous. Regex validator, no "Present", no year-only. |
| T-4.6 | Current month and year substitution for ongoing roles | TOOL | System clock. A model writing today's date from memory is a defect. |
| T-4.7 | Conventional section headers only | TOOL | Allowlist. |
| T-4.8 | docx render | TOOL | |
| T-4.9 | Margins, alignment, spacing, paragraph breaks (v0.6) | TOOL | |
| T-4.10 | Plain-text extraction round-trip check | TOOL | Runs in the Team Lead pass per v0.9, not Phase 4. Extract from the produced docx, verify no scrambling, merged sections, or dropped fields. Deterministic round trip. A failure is Critical severity, not advisory. |
| T-4.11 | Page count | TOOL | **The model cannot count pages.** Requires render-then-measure. Estimating from character count is how a resume lands at 1.4 pages. |
| T-4.12 | Remaining page space measurement (v0.8) | TOOL | Measured on the render. Feeds T-8.16. |
| T-4.13 | Filename pattern | TOOL | Decided 2026-07-23. Tailored output: `[Last]_[First]_Resume_[Company]_[RoleAbbrev]_[Version].docx` and the matching CoverLetter form. Company and role abbreviation are both required, since multiple roles at one company would otherwise collide. Version increments on regeneration rather than overwriting, sourced from package state in the profile file. No date on tailored files. Master: `[Last]_[First]_Resume_Master_[Date].docx`, with a version suffix only when several masters are produced the same day. Supersedes v0.4's `[Date]_[Version]` pattern. |
| T-4.14 | Contact block field order and completeness | TOOL | Exactly four pipe-delimited fields in fixed order: email, phone, location, LinkedIn. Blank-but-present when unavailable, so a missing field cannot shift the fields after it. |
| T-4.15 | Six-second scannability | JUDGMENT | "Bold leads tell the career story without reading body text" is a reading test. Critic pass. |
| T-4.16 | Most impressive work above the fold | JUDGMENT | Requires ranking the work. The fold position itself is TOOL-measurable and should be handed to the reviewer. |

## 7. Phase 5: Fit Check

| # | Item | Verdict | Reasoning |
| --- | --- | --- | --- |
| T-5.1 | Fit check runs before any tailoring, every submission | GATE | EARS event-driven. Sequencing enforced in control flow, not in prose the model may skip when the fit looks obvious. |
| T-5.2 | Empty registry blocks Fit Check and Tailoring | GATE | EARS unwanted-behavior. Count check. |
| T-5.3 | Map JD requirements and themes to the registry | JUDGMENT | |
| T-5.4 | Surface strong matches | JUDGMENT | |
| T-5.5 | Identify real gaps, named plainly | JUDGMENT | Critic required. This is where the "complex global structure" error originated: a gap stated inaccurately is worse than a gap omitted. |
| T-5.6 | Market compensation search | TOOL | Web search with a structured query. |
| T-5.7 | Compensation reliability assessment | JUDGMENT | Whether returned ranges are comparable to this role and market. |
| T-5.8 | No fabricated range when the search fails | GATE | EARS unwanted-behavior. The tool must be able to return "no reliable result" as a terminal state the model cannot overwrite. |
| T-5.9 | Minimum-qualification gap handling | HUMAN | Resolved 2026-07-23 in favor of v0.4. The fit check names the gap plainly and never blocks. The user decides whether to proceed. A drop-the-JD rule is user workflow, not product behavior, and does not enter the spec. |

## 8. Phase 6: Tailoring

| # | Item | Verdict | Reasoning |
| --- | --- | --- | --- |
| T-6.1 | JD ingest (paste; URL scrape post-V1) | TOOL | |
| T-6.2 | Extract the 5-6 most important requirements | JUDGMENT | Ranking requirements by importance is the substance of the phase. |
| T-6.3 | Map each requirement to the strongest matching fact | JUDGMENT | Critic required. This is where JD-matching pressure produces fabrication, failure pattern (d). |
| T-6.4 | Reorder sections and bullets | JUDGMENT | Comparative relevance. |
| T-6.5 | Semantic alignment, keywords attached to action and result | JUDGMENT | The rule explicitly rejects a mechanical substitute, so it cannot have one. |
| T-6.6 | Rewrite SUMMARY (v0.7: 3-5 bullets) | JUDGMENT + TOOL | Content is judgment; bullet count is a counter. |
| T-6.7 | Rewrite HEADLINE to exact posting title plus 3-4 registry skills | JUDGMENT + TOOL | Skill selection is judgment. Exact-title match and registry membership are both mechanical, and both should hard-fail. |
| T-6.8 | Flag JD phrases with no verbatim match | TOOL | EARS event-driven. Pure string diff. Output is an informational list. |
| T-6.9 | Never auto-insert a flagged phrase | GATE | The decision is already locked. It belongs in code precisely so the model cannot talk itself into inserting one under matching pressure. |
| T-6.10 | Replace internal names and custom-listed terms | TOOL | Same registry as T-3.15. |
| T-6.11 | Trim or compress non-relevant content | JUDGMENT | |
| T-6.12 | No-invention constraint | TOOL + GATE | Every span in generated output carries a fact id. Spans with no id, or ids not in the registry, fail the gate. Provenance-based rather than heuristic, contingent on the generation step emitting ids. See section 16. |
| T-6.13 | `[ADD METRIC: ...]` marker placement (v0.5) | JUDGMENT | Recognizing that a claim wants a metric it does not have. |
| T-6.14 | Unresolved marker sweep before delivery | GATE | No document ships with a bracketed marker in it. Trivial and absolute. |
| T-6.15 | Carry Fit Check gaps forward to the cover letter | TOOL | State handoff. |
| T-6.16 | PROJECTS inclusion decision | JUDGMENT | A populated PROJECTS section is included only where it strengthens the application for this posting, or on explicit user request. The only section whose output presence is a relevance call rather than a flag. Critic pass, since the failure mode is padding a tailored resume with unrelated work. |

## 9. Phase 7: Cover Letter

| # | Item | Verdict | Reasoning |
| --- | --- | --- | --- |
| T-7.1 | Paragraph count (v0.6: four, superseding v0.4's five) | TOOL | Count. |
| T-7.2 | Word count 250-400, single page (v0.6) | TOOL | Count plus render measurement. |
| T-7.3 | Closing line default | TOOL | Amended 2026-07-24: no longer a locked string. Iris supplies the default wording on every letter and verifies that a closing line is present and non-empty. Equality checking is dropped, since the user may edit or replace it. A replacement is user-authored text under T-7.14. |
| T-7.4 | Salutation validity | HYBRID + GATE | The ban on "To Whom It May Concern" is a gate. Validating the salutation against four allowed shapes is a tool. Choosing which tier of the fallback hierarchy applies depends on what is known about the contact, which is judgment. |
| T-7.5 | Physical formatting (v0.6) | TOOL | Left-aligned, single-spaced, 1-inch margins, blank-line breaks, font matching the paired resume. |
| T-7.6 | Honest gap naming | JUDGMENT | Critic required. The specific Google-complex-global-structure error is narrow enough to add as a banned assertion (TOOL); the general rule is not enumerable. |
| T-7.7 | Manufactured-gap detection | JUDGMENT | The SentiLink case: naming a gap the JD's own wording does not treat as one. Requires reading the JD's framing against the letter's concession. Critic. |
| T-7.8 | Gap-removal acknowledgment step | GATE + HUMAN | v0.4 leaves this an Open Question and leans toward required acknowledgment. Make it a gate: a user may soften a gap, but silent removal of a flagged finding should be structurally impossible. |
| T-7.9 | Letter of Interest routing when no JD exists | TOOL | Presence of a JD is a boolean. |
| T-7.10 | Letter of Interest content | JUDGMENT | |
| T-7.11 | Conditional paragraph by employer allowlist | TOOL | Out of V1 scope. Generalizes to a user-defined conditional block, but no user need is established beyond one. |
| T-7.12 | Portfolio-absence handling | TOOL trigger + JUDGMENT | Tool flags that the JD requests a portfolio; model writes the honest treatment. Generalizes cleanly: any user under an IP restriction hits this. Keep in V1. |
| T-7.13 | Cover letter length authorization | HUMAN | 250 to 400 words is a research-grounded default. Exceeding it requires user authorization for that specific letter with a stated rationale. The model may recommend, never decides. |
| T-7.14 | User-authored text handling | TOOL | Text the user writes or overrides is tagged as user-authored. Language and formatting checks still run against it, findings surface as advisory, and nothing gates on them. Iris never rewrites user-authored text. Provenance: user-authored spans carry no registry fact id and are exempt from T-6.12, which would otherwise fail them for having no antecedent. |

## 10. Phase 8: Final Review

v0.4 already mandates programmatic verification throughout this phase. The tiers differ in what they consume, not in that they are three prompts.

**Critical pass**

| # | Item | Verdict | Reasoning |
| --- | --- | --- | --- |
| T-8.1 | Claim supportability against the registry | JUDGMENT | Whether a claim is supported by a fact requires reading both. |
| T-8.2 | Exact value match against registry entries | TOOL | EARS unwanted-behavior, and the v0.3 FORGE Critical. An altered value is Critical even when it sounds plausible, which is precisely why a model cannot be the check: a model reading a plausible wrong figure accepts it. Values are per-user registry contents, not spec content. |
| T-8.3 | Added-clause claim check (v0.9) | HYBRID | Diff tailored against master, isolate added spans, check each against the registry with full rigor. The diff is code; the check is judgment. Failure pattern (a). |
| T-8.4 | Label-delivers-on-body check (v0.9) | JUDGMENT | Dedicated critic, no tool component available. Also runs at Master Build per T-2.3; this is the second pass on tailored text. A label promising a finding the body never states is invisible to every mechanical check because every sentence is true. Failure pattern (b). The cleanest judgment-only rule in the system. |
| T-8.5 | Missing required sections | TOOL | Checks the output-required flag for the artifact type, per T-0.6. The predicate is now defined; this Critical-severity gate previously had no specified input. |

**Pedantic pass**

| # | Item | Verdict | Reasoning |
| --- | --- | --- | --- |
| T-8.6 | Full slop scan (all Phase 3 tools) | TOOL | v0.4 already specifies this tier as a programmatic scan. |
| T-8.7 | Per-bullet word limit (default 60) | TOOL | EARS state-driven. Counter. Amended 2026-07-24: 60 is a research-grounded default rather than a fixed ceiling. Over-limit bullets flag and require per-instance authorization recorded by T-8.21, not a configuration change. Supersedes the 2026-07-23 fixed-limit decision while preserving its reasoning: an authorization does not raise the ceiling for any other bullet. |
| T-8.8 | Same-figure internal consistency | TOOL | Extract every numeral with its context, cluster by referent, flag divergence. Catches "150 managers" appearing three times with two different values inside one document. Deterministic and cheap. |
| T-8.9 | Date and figure cross-check against master | TOOL | Extraction plus comparison. |
| T-8.10 | Locked-fact scope check | TOOL | Presence check driven by `co_occurs_with`. If a fact declaring a co-occurrence partner appears and the partner does not, the check fails. Was JUDGMENT; the data model absorbs it. This is the check that failed on four resumes at once. |

**Team Lead pass**

| # | Item | Verdict | Reasoning |
| --- | --- | --- | --- |
| T-8.11 | Reviewer judgment: voice, argument strength, would it generate a call | JUDGMENT | v0.9 reframed this tier as reviewer judgment rather than a checklist. Keep it that way. |
| T-8.12 | Em-dash sweep | TOOL | |
| T-8.13 | Straight-quote and illegal-character scan | TOOL | |
| T-8.14 | AI-writing-detection pass | TOOL feeding JUDGMENT | Detectors produce signals; the reviewer weighs them. |
| T-8.15 | Full ATS scan | TOOL | |
| T-8.16 | Adversarial space-fill (v0.8) | TOOL + JUDGMENT | Tool reports unused space and enumerates every unused master bullet across every role. Choosing what to pull in is judgment. The enumeration must be exhaustive in code, because "checked against every bullet, not a glance" is exactly what a model does not reliably do. |
| T-8.17 | Run-on and jargon checks folded into TL (v0.9) | HYBRID | Nominated by T-3.13 and T-3.16, weighed here. |

**Gates**

| # | Item | Verdict | Reasoning |
| --- | --- | --- | --- |
| T-8.18 | Open Critical blocks delivery of both documents | GATE | EARS state-driven. |
| T-8.19 | Repeat-Critical escalation, no second auto-fix attempt | TOOL | Fingerprint the finding, count attempts, escalate at two. State machine, not judgment. |
| T-8.20 | Every check emits a visible pass/fail; model assertion is insufficient | GATE | The strongest rule in v0.4 and the one that most directly encodes this pivot. A check with no underlying scan cannot clear Critical or Pedantic. |
| T-8.21 | Limit override authorization record | TOOL | Records which limit was exceeded, on which artifact, with the user's stated rationale, into package state in the profile. Without the record an authorization is indistinguishable from an unnoticed violation. |

## 11. Harness level

| # | Item | Verdict | Reasoning |
| --- | --- | --- | --- |
| T-9.1 | Spec load and prompt caching | TOOL | The spec is pinned context. Cached globally, since one artifact serves every user. |
| T-9.2 | Lazy registry and inventory section retrieval | TOOL | One tool call per section beats every section in every request. |
| T-9.3 | Recognize that a conversational decision changes a rule | JUDGMENT | |
| T-9.4 | Generate the amendment diff | TOOL | |
| T-9.5 | Commit the amendment | GATE + HUMAN | Never auto-commits. Propose, show diff, wait. |
| T-9.6 | Turn-completion check | GATE | The new rule. If a decision was made this turn and no diff was produced, the turn is incomplete. Enforce in the harness, because the failure being corrected is a model narrating a change and not writing it. |
| T-9.7 | Batch state (prior batches closed) | TOOL | |
| T-9.8 | Version-locking of submitted packages | TOOL | V1.5 in v0.4. Once a package is marked submitted, its version is frozen and regeneration produces the next version rather than overwriting. State lives in the profile file per T-2.14. |
| T-9.9 | Output delivery plus Move-Item command | TOOL | |
| T-9.10 | Authentication | TOOL | V1. Required before data can be scoped to anyone. |
| T-9.11 | Session-scoped data store | TOOL | Registry, term lists, and preferences held per session and discarded at logout. No persistence. |
| T-9.12 | Cross-user isolation at the tool boundary | GATE | User data enters model context only through a tool call scoped by authenticated identity. Never two users' data in one context with an instruction to keep them apart. A cross-user leak of a custom term list means one user's employer-confidential names in a stranger's cover letter. Structurally impossible, not prompted against. |
| T-9.14 | Get today's date for filename generation | TOOL | Returns the current date in YYYY-MM-DD format. Called before rendering a master resume so the filename uses today's date rather than a date from the source document. |
| T-9.13 | Concurrency safety | TOOL | Multiple simultaneous sessions assumed from V1. |

---

## 12. EARS requirements mapped to enforcement

| EARS requirement | Enforced by | Buildable today |
| --- | --- | --- |
| Critical open, do not deliver | T-8.18 | Yes |
| JD submitted, run Fit Check first | T-5.1 | Yes |
| Value mismatch against registry, flag Critical | T-8.2 | Yes. Data model settled 2026-07-23, section 16 |
| Empty registry, block Fit Check and Tailoring | T-5.2 | Yes |
| Low-confidence extraction, route to manual review | T-0.2, T-0.3 | Yes. Threshold set 2026-07-23 |
| No reliable comp result, state so | T-5.8 | Yes |
| Never insert hidden text | T-3.2 | Yes |
| Never use an em dash | T-3.1 | Yes |
| Bullet over word limit, flag in Pedantic | T-8.7 | Yes. Fixed at 60 |
| Section approved, lock its facts | T-2.10 | Yes. Data model settled 2026-07-23, section 16 |
| Tailoring complete, flag unmatched JD phrases | T-6.8 | Yes |
| Format all date ranges Mon YYYY - Mon YYYY | T-4.5 | Yes |
| Cover letter outside word count bounds, flag in Pedantic | T-4.5, T-7.2 | Yes |
| Plain-text extraction failure, flag Critical | T-4.10 | Yes |
| Every generated span carries a registry fact id | T-6.12 | Yes, contingent on the generation step emitting ids |
| Tool call returning data outside the authenticated user's scope, fail the call | T-9.12 | Yes |
| Phase 1 Critical undispositioned, do not advance to Phase 2 | T-1.8 | Yes |
| Profile master fingerprint mismatch, warn and proceed | T-2.19 | Yes |
| Inventory-required section empty, do not complete Phase 2 | T-0.6 | Yes |

All nineteen EARS requirements are buildable as of 2026-07-24.

## 13. What v0.4 does not say

These decisions exist only in the handoff. Every one of them must land in Phase 2, and this table is the write-back gap made explicit.

| Round | Decision | Affects |
| --- | --- | --- |
| v0.5 | careerInventory Schema subsection added | T-0.6 |
| v0.5 | Numerals not spelled out | T-3.8 |
| v0.5 | `[ADD METRIC: ...]` marker, never invent a metric, covers Fix It rewrites | T-6.13, T-6.14 |
| v0.5 | Cover letter closing line locked to exact wording, not user-configurable | T-7.3, contradicts v0.4 text |
| v0.5 | Role abbreviation required in both tailored filename patterns | T-4.13, conflicts with v0.4's `[Date]_[Version]` pattern |
| v0.6 | Cover letter: four paragraphs, 250-400 words, single page | T-7.1, T-7.2, supersedes v0.4's five-paragraph structure |
| v0.6 | Cover letter physical formatting rules | T-7.5 |
| v0.6 | Salutation fallback hierarchy, "To Whom It May Concern" banned | T-7.4 |
| v0.6 | Weak passive-voice-hedge check | T-3.11 |
| v0.6 | Font family and size locked | T-4.4 |
| v0.6 | Plain-text extraction check in Final Review | T-4.10 |
| v0.7 | SUMMARY changed from paragraph to 3-5 bullets | T-6.6 |
| v0.8 | Adversarial space-fill check; 1-2 page target is a floor, not a ceiling | T-4.12, T-8.16 |
| v0.9 | Run-on and jargon checks folded into Team Lead pass | T-3.13, T-3.16, T-8.17 |
| v0.9 | Team Lead pass reframed as reviewer judgment, not a checklist | T-8.11 |
| v0.9 | Critical: added clauses checked against registry with full rigor | T-8.3 |
| v0.9 | Critical: every bullet label checked against its own body | T-8.4 |

Note what v0.4 also lacks with no version attached: any resume page-length target at all. The 1-2 page floor exists only as a job-search convention. If Iris ships to other users, that number needs a written home.

## 14. Calls most worth pushing back on

1. *(resolved 2026-07-23, see T-5.9)*
2. *(ratified 2026-07-23: T-3.6 stays TOOL.)*
3. *(ratified 2026-07-23: T-3.9 through T-3.13 stay HYBRID.)*
4. **8.6 through T-8.10, the Pedantic tier as entirely code.** v0.4 already calls this tier a programmatic scan, so this enforces rather than changes it, but the tier now contains no model call at all. Every documented Pedantic-tier failure (figure drift, the AHT stat vanishing from four resumes at once, dropped locked facts) is a value-matching problem, and value matching is what code does best and models do worst.
5. *(superseded 2026-07-23: provenance moved T-6.12 to TOOL + GATE, see section 16.4.)*
6. *(ratified 2026-07-23: the label check runs at Master Build as well as Final Review. See T-2.3.)*

## 15. Blocking gaps for Phase 2

- *(resolved 2026-07-23: Locked Facts Registry data model settled. See section 16.)*
- **The six service names and boundaries**, and how nine phases map onto them.
- *(resolved 2026-07-23: no fixed section count, required/optional flags instead. See T-0.6.)*
- *(resolved 2026-07-23: filename pattern and versioning set. See T-4.13.)*
- *(resolved 2026-07-23: extraction threshold set, word limit fixed at 60. See T-0.2 and T-8.7.)*
- *(resolved 2026-07-23: product for other job seekers. Authentication in V1, storage in V2, user state in a portable profile file. See section 0.)*

---

## 16. Locked Facts Registry data model

Settled 2026-07-23. Resolves the largest gap in v0.4, which references the registry as load-bearing in six places and defines it nowhere.

### 16.1 Fact types

Six types, not one flat table. The checks in v0.4 need different enforcement, and a single fact record forces them all through string matching.

| Type | Example shape | Enforced by |
| --- | --- | --- |
| Metric | a numeric result with a unit | Exact value match (T-8.2) |
| Date span | a start and end month/year | Format tool (T-4.5) plus exact match |
| Entity | employer, title, credential, publication, tool | Exact string match |
| Claim | a qualitative assertion about work performed | Supportability judgment (T-8.1). No string match possible |
| Skill | a named hard skill | Set membership for HEADLINE (T-2.7) and JD mapping (T-5.3) |
| Phrasing lock | a proprietary term that must never be paraphrased | Presence plus synonym prohibition |

### 16.2 Fields

`id`, `type`, `value` (write-once), `statement` (canonical approved prose), `variants`, `source`, `role_ref`, `status`, `supersedes`, `co_occurs_with`.

Three carry the weight.

**`variants`** is what makes v0.4's rule checkable. The spec allows a fact to be reordered, reframed, or omitted while forbidding any change to its value. Without an approved-variant list, the value-match tool either fires on every legitimate reframe or loosens until it stops catching drift. Variants are the seam between the two. New variants require user approval (T-2.9b), so the model cannot widen its own constraints.

**`status` plus `supersedes`** replace editing. A corrected figure retires rather than overwrites, so the registry retains a record of what was true when a package shipped. This is the NTX case: superseded figures remain live in already-shipped packages, and an overwriting registry would have erased the evidence.

**`co_occurs_with`** converts a judgment item into a tool. The rule that a locked stat must appear wherever its context appears was T-8.10, JUDGMENT, and it is the check that failed on four resumes at once. Expressed as data on the fact rather than as reviewer attention, it becomes a presence check.

### 16.3 Granularity rule

A fact is the smallest independently verifiable assertion. One resume bullet typically yields three or four. Coarser granularity prevents the value-match tool from isolating what drifted.

### 16.4 Provenance assumption

Generation emits fact ids alongside text, so every span in a tailored document carries provenance.

This is the load-bearing assumption of the model. With it, no-invention (T-6.12) and the added-clause check (T-8.3) become set operations. Without it, both stay heuristic, since there is nothing to diff against except the master's prose. It costs discipline in the generation step. If it is ever abandoned, T-6.12 reverts to HYBRID and T-8.3 loses its mechanical half.
