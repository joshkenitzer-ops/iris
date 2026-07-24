# Iris Product Spec

**Repository artifact.** Loaded as pinned context by the Iris harness. Git history is the audit trail; every rule change is a commit with a diff and a timestamp.

Supersedes the Hermes Product Spec line, v0.1 through v0.9. Manual version bumps are retired. Product name changed from Hermes to Iris on 2026-07-21.

Companion file: `iris-tool-list.md`. This document states rules. The tool list is the enforcement inventory. The two files change at different rates and are versioned separately.

**Citation convention.** Tool-list items carry a `T-` prefix and are cited inline as `(T-3.1)`. Bare decimal numbers in this file are its own section numbers and never refer to the tool list. The prefix exists because the two numbering schemes otherwise collide: section 5.9 here and item 5.9 there are unrelated rules.

Naming: this file is the spec. **Constitution** names its stable tier (Part I), not the file.

---

## How this file is organized

**Part I, Constitution.** The stable tier. Core rules. Changes rarely. Every change requires the owner's explicit sign-off.

**Part II, Decision Log.** Specific calls, appended freely, dated. Periodically consolidated upward into Part I.

**Amendment protocol.** Binding on the development harness and on any model editing this file. It does not bind Iris itself: Iris operates under the spec at runtime and has no authority to amend it.

1. A decision that changes a rule is written into this file in the same turn it is made. Narrating a change without writing it is an incomplete turn.
2. The model drafts the amendment as a diff and shows it. It never edits this file silently.
3. The diff is committed only after explicit confirmation from the owner.
4. New calls append to Part II. Promotion into Part I is a separate, deliberate act.
5. Threshold values tuned against real documents live in code config, not in this file. Tuning must not require a spec amendment.

This protocol exists because the failure it prevents already happened: decisions v0.5 through v0.9 were made and logged narratively across five rounds, and never written back into the spec.

---

# PART I: CONSTITUTION

## 1. Purpose

Iris is Lore's job seeker pipeline. It takes a user from raw career history to a polished, ATS-compliant, tailored application package, resume and cover letter alike, in a single guided experience. The pipeline is self-contained: users never need to leave the app or use another tool.

The myth is exact. Iris is the messenger goddess who moves between worlds. The product moves job seekers from where they are to where they need to be.

**1.1 Core capability.** Iris accepts a user's starting material (a performance document, an existing resume, or nothing), guides them through building a complete master resume, checks their fit against any submitted job description before committing to a full tailored build, and produces a tailored, verified, ATS-compliant resume and cover letter pair ready to submit.

## 2. Problem Statement

Four compounding problems:

- **No source of truth.** No structured starting point. Most resumes are outdated, incomplete, or written to the wrong standard.
- **ATS attrition.** Generic resumes fail ATS filters before a human reads them. Keyword mismatches, formatting errors, and vague language are the primary causes.
- **Tailoring friction.** Tailoring for each role is slow and inconsistently done. Most applicants send the same document everywhere.
- **Blind tailoring.** Users invest full effort before learning whether they are a real fit, and often paper over gaps instead of naming them.

Iris addresses all four. The master resume is built once. Every application starts with an honest fit assessment. Every tailored package is generated as a pair. Quality is enforced at every stage and verified in code rather than assumed.

## 3. Design Principles

1. **Standalone.** Iris does not depend on or redirect to any other Lore tool, and does not call one at runtime.
2. **Self-contained quality.** Every review, audit, and check runs inside Iris.
3. **Human in the loop.** The user drives decisions. Iris automates execution and surfaces findings. The user reviews and approves at each stage.
4. **Master first.** The master resume is built once and tailored many times. Every application starts from a verified source of truth.
5. **Always-on enforcement.** Quality checks run continuously, not as a final step.
6. **Fit before effort.** Iris assesses fit before generating a package and surfaces real gaps. This is sequencing, not gatekeeping. The fit check always runs first and never blocks the user from proceeding.
7. **Honesty over optimization.** Gaps identified at fit check are named directly in the cover letter. Iris does not hide weaknesses behind stronger framing elsewhere.
8. **No hidden-text tactics.** Iris never inserts invisible, white-on-white, or otherwise concealed text, for any reason, including keyword matching. Every optimization is visible to a human reader. This is a safety rule, not only an honesty rule: text a human reader cannot see but a downstream parser can is a prompt-injection vector into whatever system reads the document. It is immutable and admits no exception. Because the ban is absolute, its enforcement is a positive visibility check rather than a blocklist of known concealment techniques (T-3.2).
9. **Programmatic verification.** Quality checks that can be expressed in code, word counts, banned terms, character-level formatting, are checked in code, not inferred from model output.

Principle 9 is the load-bearing rule of this document. Section 4 states how it is applied.

## 4. Enforcement Model

Every capability Iris has is classified into one of five enforcement kinds. The full item-by-item classification is in `iris-tool-list.md`.

| Kind | Definition |
| --- | --- |
| **TOOL** | Deterministic code the model must invoke. The model never performs this by reading. |
| **GATE** | Deterministic blocker. Delivery or phase advance cannot proceed while it fails. |
| **HYBRID** | Tool nominates candidates cheaply, model adjudicates. Recall from code, precision from judgment. |
| **JUDGMENT** | Constitution-guided model judgment with a dedicated second-pass critic. Never a single generation pass. |
| **HUMAN** | Escalates to the user. The model may recommend, never decides. |

Four rules govern the classification:

**4.1** A model asserting compliance, without an underlying deterministic scan, is never sufficient to clear a Critical or Pedantic finding.

**4.2** No JUDGMENT rule is trusted to a single generation pass. Every one has a named critic that reviews the output of the generator.

**4.3** A model is never invoked to perform a check that code can perform. This is a cost rule and a reliability rule at once.

**4.4** Gates in Phases 0 through 7 interrupt at the point they fire and wait for the user. A gate that reports only at the end of a pipeline run is not implemented correctly. Phase 8 is the named exception: Final Review is an end-of-run verification stage by design, and its gates are expected to batch.

The current distribution across the 135 items lives in the tool list, not here. Restating it in two files guarantees drift on the next edit.

## 5. Locked Facts Registry

**Precedence.** This section is authoritative for the registry's rules and data model. Tool-list section 16 restates it with implementation notes; where the two differ, this section governs and the tool list is corrected.

The registry is the single source of truth for every tailored version. Every number, date, and factual claim the user approves is stored as a discrete structured fact, not as prose embedded in a bullet.

**5.1 Core rule.** A locked fact can be reordered, reframed, or omitted from a given tailored version. Its value can never be altered. An altered value is a Critical finding even when the altered value sounds plausible and would otherwise appear supported.

**5.2 Fact types.** Six, because the checks differ:

| Type | Enforced by |
| --- | --- |
| Metric | Exact value match |
| Date span | Format tool plus exact match |
| Entity | Exact string match |
| Claim | Supportability judgment. No string match possible |
| Skill | Set membership |
| Phrasing lock | Presence plus synonym prohibition |

**5.3 Fields.** `id`, `type`, `value` (write-once), `statement`, `variants`, `source`, `role_ref`, `status`, `supersedes`, `co_occurs_with`.

**5.4 Variants.** An approved alternate phrasing. Without a variant list the value-match tool either fires on every legitimate reframe or loosens until it stops catching drift. New variants require user approval; the model cannot widen its own constraints.

**5.5 Corrections retire, they do not overwrite.** A corrected fact gets `status: superseded` and a successor record. The registry therefore retains what was true when a package shipped.

**5.6 Co-occurrence.** A fact may declare that it must appear wherever a partner fact appears. This converts a reviewer-attention problem into a presence check.

**5.7 Granularity.** A fact is the smallest independently verifiable assertion. One resume bullet typically yields three or four.

**5.8 Provenance.** Generation emits fact ids alongside text. Every span of generated resume or cover letter content carries a registry fact id. This is what makes the no-invention rule a set operation rather than a heuristic, and it is a requirement on the generation step in Phase 2 and Phase 6, not an optional optimization (T-6.12).

**5.9 Empty registry.** If the registry contains zero approved facts, Fit Check and Tailoring are blocked and the user is directed to complete Master Resume Build.

## 6. Pipeline

Nine phases. Each has a defined manual component and a defined automated component. The user is never asked to do what the system can do.

| Phase | Name | User does | Iris does |
| --- | --- | --- | --- |
| 0 | Starting Point | Choose entry path. Confirm extracted material. | Accepts upload or paste. Extracts and organizes career history by role and period. |
| 1 | Audit | Review findings. Decide what to address. | Adversarial audit: content gaps, voice, formatting, slop, structure. |
| 2 | Master Build | Provide missing context. Approve each section. | Drafts bullets in bold-lead format. Writes role summaries. Locks approved facts. |
| 3 | Slop Audit | Nothing. Findings surface inline. | Always-on language pattern detection. |
| 4 | Formatting | Nothing. Findings surface inline. | Always-on ATS compliance, date formatting, scannability. |
| 5 | Fit Check | Submit JD. Review fit summary. Decide whether to proceed. | Maps requirements to the registry. Surfaces matches and real gaps. Estimates compensation if undisclosed. |
| 6 | Tailoring | Review and approve tailored resume. | Maps requirements to strongest facts. Reorders. Aligns language semantically. |
| 7 | Cover Letter | Review gap language. Approve closing and personalization. | Drafts paired cover letter or Letter of Interest. Names real gaps directly. |
| 8 | Final Review | Review findings. Approve final output. | Three-tier, programmatically verified pass. |

### Phase 0: Starting Point

Three entry paths: performance document, existing resume, start from scratch. All converge on an organized career inventory ready for Phase 1.

- Colleague names are replaced with generic labels before extraction completes. Users are prompted to remove sensitive third-party content before uploading.
- **Low-confidence extraction.** If a document cannot be extracted with sufficient confidence, Iris flags it rather than presenting partial content as complete, and routes the user to manual review or another entry path before Phase 1. Confidence is evaluated per section, fail-closed. Signals: absent text layer with low OCR confidence, replacement or control character rate, failure to detect role blocks with parseable date ranges, date parse failure rate. Threshold values are code config (see amendment protocol rule 5).

### Phase 1: Audit

Five dimensions: content gaps, AI slop, voice, formatting, structure. Findings are categorized by severity and presented before Phase 2.

**Critical disposition.** A Critical finding raised at Audit must be dispositioned before Phase 2 begins: either fixed, or explicitly acknowledged with a stated reason. Acknowledgment is not dismissal. An acknowledged Critical persists and resurfaces at Final Review, where resolution is mandatory and acknowledgment is not offered (T-1.8). Severity assignment is held tight deliberately, since a rubric that over-assigns Critical converts this into a spurious block.
 The user need not act on every finding immediately; Iris carries them forward as a working checklist. Dismissals are keyed by content signature, never by run ID.

### Phase 2: Master Resume Build

The master is the source document, not a document to send.

- **Bold-lead format.** Every bullet opens with a bold three to six word descriptor followed by plain text stating what was done, the context, and the result.
- **Label delivers on body.** A bullet's label must be delivered by its own body. A label promising a finding the body never states is a defect even when every sentence in it is true. This is checked at Master Build, not only at Final Review, so a hollow label cannot propagate into tailored copies.
- **HEADLINE.** Positioned after Name and before Contact. A target title plus the strongest three to four hard skills. Mechanical, not prose, and distinct from Summary. Every skill listed must already exist in the registry. Rewritten per posting in Phase 6.
- **SUMMARY.** Three to five scannable bullets. Not a paragraph.
- **Role summaries.** One to two sentences before the bullets for each role.
- Audit findings surface as prompts during the build.
- Internal project names are flagged with a prompt for a plain descriptor.
- **careerInventory schema.** A structured object, not free text. No fixed section count. Relative order is locked: NAME, HEADLINE, CONTACT, SUMMARY, SKILLS, EXPERIENCE, EDUCATION, PROJECTS, PUBLICATIONS. Every service that reads or writes the inventory (`buildService`, `tailorService`, `docxService`) uses this same order; none may reinterpret it locally.
- **Section flags.** Two independent flags, not one. Inventory-required means the user must supply it before Phase 2 completes. Output-required means the rendered document must contain it. They come apart: HEADLINE and SUMMARY are Iris-generated, so requiring them of the user is incoherent while requiring them in output is not (T-0.6, T-8.5).

| Section | In inventory | In output |
| --- | --- | --- |
| NAME | Required | Required |
| HEADLINE | Iris-generated | Required |
| CONTACT | Required | Required |
| SUMMARY | Iris-generated | Required |
| SKILLS | Required | Required |
| EXPERIENCE | Required | Required |
| EDUCATION | Optional | Omit if empty |
| PROJECTS | Optional | Conditional, see Phase 6 |
| PUBLICATIONS | Optional | Omit if empty |

- **PROJECTS definition.** Work performed outside the scope of employment. Work performed within a role is an EXPERIENCE bullet, never a PROJECTS entry. This is a classification rule, not a judgment call (T-0.5).
- **CONTACT fields.** Exactly four pipe-delimited fields. Email, phone, and location are required and must be non-empty, location at city and state granularity and never a street address. LinkedIn is optional and blank-but-present when absent. Blank-but-present governs rendering for every field, so a missing value cannot shift the fields after it; it does not make a required field satisfiable by leaving it blank.
- Facts lock into the registry when the user approves a section (T-2.10).
- Every span of generated content carries the fact id it derives from, per 5.8. A span with no id cannot pass Final Review (T-6.12).

The user is responsible for providing context Iris cannot invent, approving each section before it locks, and confirming that every number, date, and claim is accurate and defensible.

### Phase 3: Slop Audit

Runs continuously on every draft and revision, never as a step the user initiates.

Patterns detected:

- Self-annotation: sentences explaining why a bullet is impressive instead of letting it stand.
- Triple parallel noun phrases.
- Passive weak endings, and weak passive hedges ("participated in", "assisted with", "was involved in", "contributed to").
- Colon-then-gerund constructions.
- Parallel pair endings: consecutive sentences ending on the same structural beat.
- Parallel sentence fragment triplets.
- The "not just X but Y" formula.
- Vague metrics: quantifier claims with no attached number.
- Uniform sentence cadence: a run of consecutive sentences of near-identical length and structure.
- Run-on sentences. One idea per sentence.
- Unexplained internal or proprietary program names. Every such name is explained in plain English on first use in each document, and tied back explicitly if used again. Test: the document makes sense to a reader with zero context on the user's work.
- Numbers appear as numerals, never spelled out.
- **Banned vocabulary, two tiers.** Every entry is a known LLM writing tell. They differ in how they present.
  - *Always flagged:* seamlessly, leveraged, utilized, spearheaded, synergized, through-line, established clear expectations, intellectual foundation, what I bring to this role. Any occurrence.
  - *Frequency-gated:* effectively, directly. Ordinary English in isolation, a tell when repeated within a document or used where more direct language would serve. Flagged above a per-document occurrence threshold, or on any use judged imprecise (T-3.3, T-3.3a).

  The threshold is code config, not spec content, per amendment protocol rule 5. The distinction matters because a hard ban on ordinary English produces a false positive on every draft, which trains users to ignore the check.
- User-defined banned terms: personal or employer-specific terms, internal codenames, retired jargon. Checked alongside the default list. The default list is spec content; user additions are user data.
- Em dashes. No exceptions (T-3.1).
- Hidden text of any kind. Hard constraint, never a configurable preference (T-3.2). See open item below on the gap between this rule's scope and its check's scope.

**Never invent a metric.** Where a claim wants a number the registry does not hold, Iris inserts a bracketed marker (`[ADD METRIC: ...]`) rather than supplying a figure. This applies to revision and repair operations as well as first drafts. No document ships containing an unresolved marker.

### Phase 4: Formatting

**ATS compliance.** No tables or multi-column layouts. No graphics, icons, or special characters in section headings. Contact information in plain text, not in a header or footer. Conventional section titles only. Dates formatted as `Mon YYYY - Mon YYYY` using three-letter month abbreviations; year-only dates and the word "Present" are not permitted, and ongoing roles use the current month and year at generation time.

**Fonts.** Arial, Calibri, Helvetica, Garamond, or Georgia. Body 10 to 12pt, name 11 to 14pt.

**Physical formatting.** Left-aligned, single-spaced, one-inch margins, blank-line paragraph breaks. A cover letter matches its paired resume's font.

**Six-second scannability.** Bold leads tell the career story without body text. The most impressive work appears above the fold. Role titles and dates are immediately visible.

**Filenames.** Output naming is specified in section 8 and enforced at generation (T-4.13).

**Length.** Tailored resumes target one to two pages, per resume best-practice research. The target is a floor, not a ceiling: available space is filled before content is trimmed, and relevant unused registry content is pulled in even where that pushes past two pages. Older or less relevant roles stay title-and-dates only rather than being padded to fill space. The master resume has no length ceiling; comprehensiveness is its purpose, and it is not a document the user sends.

### Phase 5: Fit Check

Runs on every job description submission, before any tailored output is generated.

- Maps the JD's requirements and themes against the registry.
- Surfaces strong, well-supported matches.
- Names real gaps plainly. Gaps are not reframed or minimized. A gap stated inaccurately is worse than a gap omitted.
- Where compensation is undisclosed, runs a market search and presents an estimated range clearly labeled as an estimate. Where no reliable result is available, states that plainly rather than presenting a fabricated or low-confidence range.
- Blocked if the registry is empty (T-5.2).

The fit check is informational. It never blocks the user from proceeding on a low-fit role. The user decides whether to proceed and how directly to name remaining gaps.

### Phase 6: Tailoring

- Extracts the five to six most important requirements from the JD.
- Maps each to the strongest matching fact in the registry.
- Reorders sections and bullets so the strongest matches lead.
- **Semantic alignment.** Keywords appear attached to a demonstrated action and result. Exact-phrase mirroring alone is never a substitute for a real match.
- Rewrites SUMMARY and HEADLINE for the role. HEADLINE takes the exact posting title plus three to four skills already in the registry.
- Flags and replaces internal project names and user-listed terms.
- Trims or compresses content not relevant to this application.
- **JD phrase flagging.** Notable JD phrases with no verbatim match anywhere in the tailored resume are surfaced as an informational list. Iris never auto-inserts them. The user decides per phrase whether an exact-wording swap fits honestly within the alignment already produced.
- Carries Fit Check gaps forward to the cover letter.

**PROJECTS inclusion.** A populated PROJECTS section is included in a tailored resume only where it strengthens the application for that posting, or where the user explicitly asks for it. Unlike every other optional section, presence in the inventory does not imply presence in output (T-6.16).

**No invention.** Every span of tailored content carries a registry fact id, per 5.8. Spans with no id, or with ids absent from the registry, fail the gate (T-6.12). Iris adds nothing that is not in the registry. Tailoring is reordering and reframing. Every detail added during tailoring is a new claim requiring its own source check: an added qualifier, a modality breakdown, a geographic scope, an audience descriptor, or a methodology label carried over from a different role.

### Phase 7: Cover Letter

Generated as a pair with every tailored resume, from the same JD and the same Fit Check findings.

- **Structure.** Four paragraphs: opening hook with role reference; core capability argument built on the two to three strongest matched requirements with quantified evidence; company alignment, which also carries honest treatment of any real gap from the Fit Check; closing restating value and ending on the locked line. 250 to 400 words, single page. These bounds are a research-grounded default, not a hard ceiling. Exceeding them requires the user's authorization for that specific letter, with a stated rationale, recorded in package state (T-7.13).
- **Closing line.** Default wording, user-adjustable: "I look forward to exploring whether this is the right fit for both of us." Iris supplies it on every letter. The user may edit or replace it. Any replacement is user-authored text and follows the rule below (T-7.3).
- **User-authored text.** Where the user writes or edits text directly, Iris still runs its language and formatting checks against it and surfaces findings, but those findings are advisory and do not gate delivery. Iris never silently modifies text the user wrote. This applies to the closing line and to any other passage the user supplies or overrides (T-7.14).
- **Salutation.** Named contact, then department, then company recruiting team, then "Dear Hiring Manager". Never "To Whom It May Concern".
- **Gap language.** Real gaps from the Fit Check are named directly and specifically, never omitted or reframed as strengths. The user may adjust how directly a gap is named. Silent removal of a flagged finding is structurally prevented; removal requires acknowledgment.
- **No manufactured gaps.** A gap the JD's own wording does not treat as a gap is not conceded. Conceding one undermines the application without cause.
- **Portfolio absence.** Where a posting requests a portfolio the user cannot supply, the letter addresses the absence honestly rather than fabricating one.
- Same slop and formatting standards as the resume.
- **Letter of Interest.** Where no JD exists, Iris generates a Letter of Interest instead, on the same fact base and honesty standard, structured around the company's public work.

### Phase 8: Final Review

Three tiers run on the completed pair before delivery. Every check expressible in code is run in code. Every check produces a visible pass or fail result.

**Critical pass.** Claims unsupported by the registry. Any value not exactly matching its registry entry. Formatting failures. Missing sections flagged output-required for this artifact type (T-8.5). Two specific checks:

- Every explanatory or clarifying clause added during tailoring is checked against the registry with the same rigor as an original claim. Added text is a common place for unsupported claims to enter unnoticed.
- Every bullet label is checked against its own body.

**Pedantic pass.** Entirely programmatic. Full slop scan. Per-bullet word limit, default 60. A bullet over the limit is flagged and may ship only with the user's authorization for that specific bullet, with a stated rationale, recorded in package state. This is not a configurable setting: a config value silently raises the ceiling for every future bullet, while an authorization is one decision about one bullet and leaves a record (T-8.7, T-8.21). Same-figure internal consistency: every instance of a figure within a document must agree. Date and figure cross-check against the master. Co-occurrence presence check.

**Team Lead pass.** Reads the document as an experienced hiring reviewer applying real judgment, not a checklist run on autopilot. Assesses voice consistency, argument strength, and whether the document would generate a call. Deterministic components run as tools and hand their results to the reviewer: em-dash sweep, straight-quote and illegal-character scan, AI-writing-detection pass, full ATS scan, the plain-text extraction check, and the adversarial space-fill measurement. The extraction check round-trips the generated docx back to text and verifies it against scrambled characters, merged sections, and dropped fields. A failure is Critical severity, not a Team Lead advisory.

**Adversarial space-fill.** Before finalizing, remaining page space and unused relevant registry content are enumerated exhaustively, every bullet across every role, not sampled. The reviewer decides what to pull in.

**Severity handling.** Critical findings must be resolved before either document is delivered (T-8.18). High findings are surfaced with recommended fixes. Medium and Low are advisory. Findings are terse: issue and fix. Unsupported claims are cut rather than softened. If the same Critical finding recurs after a fix attempt, Iris surfaces it to the user rather than attempting the same automated fix again.

## 7. Data, Identity, and Privacy

**7.1** Authentication is in V1. Account-based storage is V2. Identity without content.

**7.2** No PII is persisted in V1. User state travels in a portable **Iris Profile**: a single downloadable markdown file the user holds and re-uploads at session start. Sections: Locked Facts Registry, custom term lists, preferences, dismissed findings, package state.

**7.3** One artifact, not several. The user already carries their master docx separately, and multiple state files multiply the same failure of one going missing or stale.

**7.4** Profile integrity is checksummed on export and verified on import. This guards against truncation and corruption, not user editing. The registry constrains the model, not the user, who owns the facts.

**7.5** Dismissed findings persist across sessions, keyed by content signature. Revised text yields a new signature and the finding correctly returns. Critical findings are never dismissible.

**7.6** Multiple concurrent users are assumed from V1. User data enters model context only through a tool call scoped by authenticated identity. Two users' data are never placed in one context with an instruction to keep them apart.

**7.7** Output documents carry no Lore branding and no Iris state. They are the user's documents, ready to submit without modification.

**7.8** The profile records a fingerprint of the master it was built from. On import, a mismatch against the uploaded master warns the user, is recorded in the session log, and does not block. Warning rather than blocking is deliberate: a recorded divergence is interpretable when something later goes wrong, while a hard block teaches users to work around the check (T-2.19).

## 8. Output

Every output is a downloadable docx. No onscreen editor; users edit in their own word processor.

- Master: `[Last]_[First]_Resume_Master_[Date].docx`. A version suffix is added only when several masters are produced the same day.
- Tailored resume: `[Last]_[First]_Resume_[Company]_[RoleAbbrev]_[Version].docx`
- Cover letter: `[Last]_[First]_CoverLetter_[Company]_[RoleAbbrev]_[Version].docx`

Company and role abbreviation are both required on tailored output; multiple roles at one company would otherwise collide. Version increments on regeneration, sourced from package state in the profile.

## 9. Core Requirements (EARS)

The backbone enforcement rules, stated unambiguously rather than inferred from prose.

| Pattern | Requirement |
| --- | --- |
| State-driven | While a Critical finding is open in Final Review, Iris shall not deliver the tailored resume or cover letter. |
| Event-driven | When a job description is submitted, Iris shall run the Fit Check before generating any tailored output. |
| Unwanted-behavior | If a value in a tailored output does not exactly match its registry entry, then Iris shall flag it as a Critical finding. |
| Unwanted-behavior | If the registry contains zero approved facts, then Iris shall block Fit Check and Tailoring. |
| Unwanted-behavior | If a document cannot be extracted with sufficient confidence, then Iris shall flag the extraction and route the user to manual review before Phase 1. |
| Unwanted-behavior | If the market compensation search returns no reliable result, then Iris shall state that compensation could not be estimated rather than presenting a fabricated range. |
| Ubiquitous | Iris shall never insert hidden, invisible, or white-on-white text into any output, for any reason. |
| Ubiquitous | Iris shall never use an em dash in any generated output. Generated output means any resume, cover letter, or user-facing text Iris produces. This spec is held to the same standard by convention, not by this requirement. |
| State-driven | While a bullet exceeds 60 words without a recorded authorization, Iris shall flag it in the Pedantic pass. |
| Event-driven | When the user approves a Master Resume section, Iris shall lock all facts in that section into the registry. |
| Event-driven | When Tailoring completes, Iris shall flag any notable JD phrase with no verbatim match as a list surfaced to the user. |
| Ubiquitous | Iris shall format all Experience and Projects date ranges as Mon YYYY - Mon YYYY, never year-only or the word Present. |
| State-driven | While a cover letter falls outside 250 to 400 words without a recorded authorization, Iris shall flag it in the Pedantic pass. |
| State-driven | While a Phase 1 Critical finding is without disposition, Iris shall not advance to Phase 2. |
| Unwanted-behavior | If the imported profile's master fingerprint does not match the uploaded master, then Iris shall warn the user, record the mismatch, and proceed. |
| State-driven | While a section flagged inventory-required is empty, Iris shall not complete Phase 2. |
| Unwanted-behavior | If the plain-text extraction check reveals scrambled characters, merged sections, or dropped fields, then Iris shall flag it as a Critical finding. |
| Ubiquitous | Iris shall attach a Locked Facts Registry fact id to every span of generated resume or cover letter content. |
| Unwanted-behavior | If a tool call would return data not scoped to the authenticated user, then Iris shall fail the call rather than return the data. |

All nineteen are buildable. Fourteen carried from v0.9; provenance and cross-user isolation added 2026-07-24 after adversarial review found both load-bearing and unrequired; Phase 1 Critical disposition and profile fingerprint mismatch added 2026-07-24 by owner decision. Length limits are defaults subject to per-instance authorization, not configured values.

## 10. Scope Boundary

**V1 requires work history.** EXPERIENCE is inventory-required, so a user with no work history is blocked by a Critical rather than served poorly. This is deliberate and consistent with new-graduate onboarding being out of scope. It is stated here rather than left to emerge from a validator flag.

**V1.** Three entry paths. Master build with registry and bold-lead enforcement. Always-on slop and formatting checks including custom term lists. Fit Check with compensation estimate. JD-paste tailoring with semantic alignment. Paired cover letter and Letter of Interest. Three-tier programmatically verified final review. Docx output. Authentication. Portable Iris Profile.

**V1.5.** ATS scraper (URL input with automated JD extraction). Version-locking of submitted packages, locking on package state rather than filename. Verifiable-artifact prompts during Audit.

**V2.** Account-based storage. Server-side master and registry persistence. Requires a data handling policy.

**Out of scope, by decision rather than omission.** Onscreen editor: users edit in their own word processor. New-graduate and no-career-history onboarding: needs dedicated research before it can be specced.

## 11. Relationship to the Lore Suite

Iris is a standalone product. It does not call Cassandra, Vulcan, or any other Lore tool at runtime. Its audit and review logic is purpose-built for resume and job application work, and the Locked Facts Registry and Fit Check logic are internal.

The three-tier Phase 8 verification pipeline, the Fit Check phase, and the honest-gap cover letter standard originate in the owner's own application workflow and are generalized here for all users.

Design-time review of this spec by another Lore tool is not a runtime dependency and does not conflict with this section.

---

# PART II: DECISION LOG

Append freely. Consolidate upward into Part I periodically.

## 2026-07-23: Architecture pivot

Iris moves from six deterministic services calling the model at fixed points to an agentic harness where this file is pinned context. Rearchitecture, not refactor. Git supersedes manual version bumps. Prompt caching applies to this file and to the registry; individual inventory sections are retrieved on demand rather than loaded wholesale.

## 2026-07-23: Consolidation of v0.1 through v0.9

The prior spec line is absorbed into Part I.

**Correction, 2026-07-23.** This entry originally stated that v0.5 through v0.9 existed only in Janus handoff prose and were being written into a spec for the first time. That was wrong. v0.9 was located later the same day and contains all five rounds, correctly folded in, with a changelog recording each. The spec-sync standing step established in v0.4 worked as designed. The actual failure was that the owner held v0.4 and was unaware v0.9 existed, which is a single-source-of-truth problem rather than a write-back problem, and is what a repo-tracked file addresses. The amendment protocol above remains correct but is not the whole fix; findability is.

| Round | Decision | Landed in |
| --- | --- | --- |
| v0.5 | careerInventory schema documented | Phase 2 |
| v0.5 | Numerals not spelled out | Phase 3 |
| v0.5 | `[ADD METRIC: ...]` marker, never invent a metric | Phase 3 |
| v0.5 | Closing line locked to exact wording | Phase 7 |
| v0.5 | Role abbreviation in tailored filenames | Section 8 |
| v0.6 | Cover letter four paragraphs, 250 to 400 words | Phase 7 |
| v0.6 | Physical formatting rules | Phase 4 |
| v0.6 | Salutation fallback hierarchy | Phase 7 |
| v0.6 | Weak passive-hedge check | Phase 3 |
| v0.6 | Font family and size locked | Phase 4 |
| v0.6 | Plain-text extraction check | Phase 8 (Team Lead pass) |
| v0.7 | SUMMARY as three to five bullets | Phase 2 |
| v0.8 | Adversarial space-fill; length is a floor | Phase 4, Phase 8 |
| v0.9 | Run-on and jargon checks into Team Lead pass | Phase 3, Phase 8 |
| v0.9 | Team Lead pass as reviewer judgment, not a checklist | Phase 8 |
| v0.9 | Added clauses checked against the registry | Phase 8 |
| v0.9 | Bullet label checked against its own body | Phase 2, Phase 8 |

Two v0.4 statements were superseded rather than absorbed: the five-paragraph cover letter, and a closing line described as both locked and user-configurable.

## 2026-07-23: Scope

Iris is built as a product for other job seekers, per the v0.4 Design Principles. Rules specific to any one user's record are user data, not spec rules. The hardcoded codename registry becomes an instance of the user-defined term list. Locked values become registry contents.

## 2026-07-23: Fit check conflict resolved

The fit check stays informational and never blocks, per Design Principle 6. A drop-the-JD rule on a minimum-qualification gap is user workflow, not product behavior, and does not enter the spec.

## 2026-07-23: Identity and storage

Authentication into V1, storage stays V2, no PII persisted. Concurrent users assumed. State travels in a single portable profile file. Dismissed findings persist, keyed by content signature; Critical findings excluded.

## 2026-07-23: Locked Facts Registry data model

Six fact types rather than one flat table. Write-once values. Approved variants as the seam between drift detection and legitimate reframing. Corrections retire rather than overwrite. Co-occurrence declared as data. Granularity set at the smallest independently verifiable assertion. Generation emits fact ids, making no-invention a set operation.

## 2026-07-23: Enforcement verdicts ratified

Uniform sentence cadence stays a deterministic tool. Five structural slop checks stay hybrid with a nominating tool in front of judgment. The label-delivers-on-body check runs at Master Build as well as Final Review. The Pedantic tier contains no model call.

## 2026-07-23: Schema, limits, and filenames

No fixed careerInventory section count; required and optional flags with locked relative order. Per-bullet word limit fixed at 60. Tailored filenames carry company, role abbreviation, and version, no date. Versioning retained; regeneration increments rather than overwrites.

## 2026-07-23: Length rule confirmed as a product rule

The one-to-two-page target for tailored resumes is retained, grounded in resume best-practice research rather than personal convention, and therefore promoted to Part I. It remains a floor rather than a ceiling. The master resume keeps no length ceiling.

## 2026-07-23: Reconciliation against v0.9

v0.9 located after this spec was drafted. Corrections applied: fourteen EARS requirements rather than twelve, adding cover letter word-count bounds and plain-text extraction failure as Critical; CONTACT includes location; the plain-text extraction check belongs to the Team Lead pass at Critical severity rather than Phase 4; cover letter paragraph three is company alignment carrying the gap, not a standalone gap paragraph; the locked closing line's exact text recorded; Core Capability and Relationship to the Lore Suite restored.

Four decisions of 2026-07-23 supersede v0.9 as later and deliberate: tailored filenames drop the date, the per-bullet word limit is fixed rather than configured, careerInventory sections take required/optional flags rather than a fixed nine, and gap acknowledgment is a gate. All four of v0.9's open questions are now closed.

## 2026-07-24: Adversarial red-team pass waived, then run internally

Owner authorization to skip the Cassandra pass, 2026-07-24. The deployment cost was not worth blocking build work. The four review priorities drafted for it (reconciliation gaps against v0.9, cross-file drift between spec and tool list, rules whose enforcement is narrower than they sound, and rules with no enforcement path) stand as the scope if an independent pass happens later.

A non-independent pass was then run in the same session by the model that wrote both documents. Its blind spots are that model's blind spots, and it is not a substitute for independent review.

## 2026-07-24: Review findings resolved

Fixed: tool-list IDs now carry a `T-` prefix, ending a collision where spec section 5.9 and tool item 5.9 named unrelated rules; the spec now cites those IDs, which it previously claimed to do and did not; provenance became a requirement in Phase 2, Phase 6, and EARS rather than a data-model note with no obligation attached; rule 4.4 names Phase 8 as its exception rather than contradicting it; section 5 is declared authoritative over tool-list section 16; enforcement counts were removed from the spec to stop them drifting; the amendment protocol names its subject and excludes Iris itself; cross-user isolation gained an EARS requirement; the stale Phase 4 row for the extraction check was corrected; filename cross-reference and em-dash scope defects closed.

EARS requirements now number sixteen. Four findings need owner input and are listed below rather than resolved.

## 2026-07-24: Four review findings resolved by owner

**Hidden text.** The ban stays absolute and gains a safety rationale: concealed text is a prompt-injection vector into any downstream parser, not merely a dishonest optimization. Enforcement inverts from a blocklist of known techniques to positive visibility verification, since a blocklist cannot back an absolute ban.

**Phase 1 Criticals.** Disposition required before Phase 2. Fixed or acknowledged-with-reason both satisfy it; acknowledgment is distinct from dismissal and the finding resurfaces at Final Review. The severity rubric is held tight so this does not become a spurious block.

**Profile mismatch.** Warn, record, proceed. A recorded divergence is interpretable later; a hard block teaches users to route around the check.

**Length limits.** Research-grounded defaults with per-instance authorization. This supersedes the 2026-07-23 decision that the 60-word bullet limit is fixed and not user-configurable. That decision's reasoning is preserved rather than discarded: an authorization is not a configuration, because it does not raise the ceiling for anything beyond the one bullet or letter it covers, and it leaves a record where a config change leaves none.

## 2026-07-24: Closing line unlocked

The cover letter closing line becomes a default rather than a locked string. The existing wording is retained as that default and the user may adjust it. Locking it was decided in v0.5 when Iris was a personal tool and was never re-examined against product scope; no rationale for enforcing one house closing line across every user survives that change.

Consequence: this introduces user-authored text inside a generated document, a category the spec did not previously have. A rule was added to Phase 7. Such text is checked and flagged but never gated on and never silently altered. User-authored spans carry no registry fact id and are exempt from the provenance gate, which would otherwise fail them for having no antecedent.

## 2026-07-24: Required section set settled

Two flags rather than one, since a single flag misstates four of the nine rows. Dispositions per the table in Phase 2.

EXPERIENCE and SKILLS are both required, superseding an earlier proposal of NAME, CONTACT, EXPERIENCE that omitted SKILLS. SKILLS carries ATS keyword survival and cannot be optional.

PROJECTS is defined by scope of employment, which resolves the EXPERIENCE-versus-PROJECTS classification ambiguity that was previously left to judgment. Its output inclusion is conditional rather than flag-driven: a relevance call plus a user override, unlike every other section.

CONTACT gains field-level flags. Email, phone, and location required; LinkedIn optional. Phone is required on best-practice grounds.

## 2026-07-24: Red-team pass closed

The pass was performed using the Cassandra review method rather than the deployed app, which the owner intends to rebuild. Treated as satisfied: fifteen findings, eleven fixed directly and four resolved by owner decision.

One caveat recorded rather than argued: the reviewer wrote both documents, so the pass was not independent and its blind spots are that author's blind spots.

## 2026-07-24: Banned vocabulary retained, check refined

All eleven inherited entries stay. They are known LLM writing tells. What changes is enforcement: the list splits into always-flagged terms and frequency-gated terms, the latter being ordinary English that reads as a tell only when repeated or misapplied. Frequency detection is deterministic; assessment of misuse is judgment and is a separate item.

## 2026-07-24: Service names closed as moot

The six service names were a blocking gap only while the plan was to map the spec onto the existing app. Under the harness architecture they are legacy. The tool list captures the service functionality in full, organized by phase rather than by service, so no spec content depends on the old boundaries.

## Open items

- **Lore palette tokens**, locked as of 2026-07-03, should be read before any Iris UI work begins. Non-blocking: brand consistency matters but gates nothing. Carried as a standing reminder rather than an unresolved decision.
