# Iris Tool List

| ID | Name | Kind | Notes |
| --- | --- | --- | --- |
| T-0.1 | ingest_document | TOOL | Parsing is solved. Model tokens spent here are waste. |
| T-0.2 | score_extraction_confidence | HYBRID | Composite, fail-closed, evaluated per section. Routes to manual review if any signal trips: no text layer and OCR mean confidence under 85%; replacement or control characters above 2% of extracted characters; fewer than two role blocks with a parseable date range; over 20% of date-like strings failing to parse. Threshold values are code config, not spec content, so tuning does not require a spec amendment. Whether partial content is still usable remains judgment. |
| T-0.3 | route_low_confidence_to_manual_review | GATE | EARS requirement. Enforcement must not be prose the model may skip when the content looks readable enough. |
| T-0.4 | redact_colleague_names | GATE | Name detection needs reading; regex misses initials and unusual names. Model flags, tool performs the substitution so the edit is auditable, gate blocks storage until clean. Note the July 21 precedent is stricter than v0.4: peer and manager feedback was excluded from the resume and from memory entirely, not name-scrubbed. Section-level exclusion is TOOL when sections are labeled. Needs your call on which rule is real. |
| T-0.6 | check_career_inventory_schema | TOOL | No fixed section count. Two flags per section, inventory-required and output-required, evaluated separately. Relative order is locked. Empty optional sections are omitted from output rather than rendered as an empty heading. CONTACT is four pipe-delimited fields with field-level flags: email, phone, and location non-empty, LinkedIn optional. Blank-but-present governs rendering, not satisfaction of a required flag. Dispositions settled 2026-07-24; see the spec's Phase 2 table. |
| T-0.7 | validate_structured_intake_form | TOOL | Form. No model. |
| T-0.8 | find_near_duplicate_candidates | HYBRID | Not in v0.4, but the 338-page export re-listed cumulative history per review cycle. Similarity clustering is cheap code; choosing the canonical version of a repeated claim is judgment, since a later instance can be a revision rather than a copy. |
| T-0.9 | check_primary_source_support | HYBRID | Not in v0.4. Full-text search of a source for a claim's distinctive tokens is a tool, and it is what caught the Large Customer Sales fabrication. Interpreting absence is judgment, and per the July 21 standing note the model does not resolve it: absence means treat as suspect and ask. |
| T-0.10 | read_attachment_text | TOOL | Added 2026-07-27. Reads a span of an already-extracted document from server-side cache, by offset. Pure retrieval, no interpretation, so TOOL. Exists because an ingest result is not read once and discarded, it is carried in the transcript and re-sent every turn: inlining a 338-page export costs ~100,000 tokens per call for the life of the session. Documents past INLINE_EXTRACT_CHARS now return a preview plus paging through this. Deciding which span is worth reading is the model's call, which is exactly why this takes an offset rather than trying to guess. |
| T-1.7 | filter_carried_forward_findings | TOOL | State. Dismissal keyed by content signature, per existing convention. |
| T-2.10 | validate_facts_for_locking | TOOL | EARS event-driven. Approval fires the write. |
| T-2.11 | detect_internal_project_names | TOOL | Match against the user's own custom term list (T-3.4). No global codename registry exists in a multi-user product. |
| T-2.13 | get_open_audit_findings_for_section | TOOL | State surfacing. |
| T-2.14 | export_iris_profile | TOOL | Single downloadable markdown file, internally sectioned: Locked Facts Registry, custom term lists, preferences, dismissed findings, package state. Package state carries version counters and submitted status per company and role, which is what makes T-4.13 versioning and T-9.8 locking possible without server storage. One artifact rather than several, since the user already carries the foundational-resume docx separately and v0.4 forbids storing anything in it. Substitutes for storage: the user keeps their own state, so V1 has no deletion obligation and no retention policy. |
| T-2.15 | import_iris_profile | TOOL | Re-upload at session start. Validates structure and version before any fact enters context. A malformed profile fails loudly rather than half-loading. |
| T-2.16 | check_profile_integrity | TOOL | Checksum on export, verified on import. Guards against truncation and corruption, not user editing. The registry constrains the model, not the user, who owns the facts and can already state a wrong number in Phase 2. |
| T-2.17 | check_facts_traceable_to_foundational | TOOL | Fallback path when no profile file exists. First session, or a user who lost theirs. |
| T-2.18 | apply_dismissed_findings | TOOL | Dismissals travel in the profile, keyed by content signature per existing convention. Revised text yields a new signature and the finding correctly returns. Critical findings are excluded: v0.4 blocks delivery on any open Critical, so they are not dismissible, and a persisted dismissal must never carry one past the gate in a later session. |
| T-2.19 | restore_registry_from_profile | TOOL | Added 2026-07-27. Writes a validated profile's Locked Facts Registry back onto the session. Deterministic deserialization, so TOOL. Exists because export/validate/apply was only two-thirds built: T-2.14 serialized the registry and T-2.15 validated it, but nothing wrote it back, so a returning user restored dismissed findings and nothing else and was then blocked at Fit Check by T-5.2. Refuses to overwrite a session that already has active facts. Restoring is not verifying: T-2.17 remains the check that a rehydrated registry still traces to a real foundational resume. |
| T-2.2 | check_bold_lead_structure | TOOL | Countable in the docx XML. Binary. |
| T-2.4 | check_role_summary_length | TOOL | Count. |
| T-2.7 | check_headline_skills_backed | TOOL | v0.4: every skill listed must already exist in the Locked Facts Registry. This is set membership. Fully mechanical, and it is the cheapest anti-fabrication check in the entire spec. |
| T-2.8 | check_headline_placement | TOOL | Position check. |
| T-2.9 | extract_facts_into_registry | HYBRID | Typing, storage, and indexing are code. Deciding where one assertion ends and the next begins is judgment, bounded by the granularity rule: a fact is the smallest independently verifiable assertion. See section 16. |
| T-3.1 | check_em_dash | GATE | EARS ubiquitous. One character class, absolute. The canonical case for never invoking a model. |
| T-3.10 | check_triple_parallel_noun_phrases | HYBRID | "X, Y, and Z" is trivially detectable. Whether it reads as slop or as accurate enumeration is judgment. |
| T-3.11 | check_passive_weak_hedges | HYBRID | POS tagging finds passive constructions deterministically. Whether the passive weakens the claim is judgment. |
| T-3.12 | check_parallel_pair_endings | HYBRID | Structural repetition is measurable. Rhetorical intent is not. |
| T-3.13 | check_run_on_sentences | HYBRID | Length, clause count, and conjunction count nominate. Whether it is two ideas or one long one is judgment. |
| T-3.15 | check_confidential_term_leak | GATE | Same engine as T-3.4, escalated to a gate. A user's employer-confidential names must never reach output. Exact match against the per-user list, with a per-user allowlist for public exceptions. Never judgment. |
| T-3.16 | check_first_use_explainer | HYBRID | Registry members are tool-detectable. Whether a non-registry proper noun needs an explainer is judgment. Failure pattern (a) applies: the explainer itself can introduce an unsupported claim, so its output routes back through T-8.3. |
| T-3.17 | nominate_tense_inconsistency_candidates | HYBRID |  |
| T-3.18 | nominate_repeated_opener_candidates | HYBRID |  |
| T-3.2 | check_hidden_text_in_docx | GATE | EARS ubiquitous. Positive visibility verification: every text run in the output must be demonstrably visible when rendered, and anything that cannot be shown visible fails. An absolute ban cannot be backed by a blocklist, so the known-pattern list (font color against background, hidden run attribute, zero-size fonts) is retained only as a fast pre-filter. Safety-critical: concealed text is a prompt-injection vector into any downstream parser. Never configurable. |
| T-3.3 | check_banned_vocabulary | TOOL | Lemma-aware match, two tiers. Always-flagged terms fire on any occurrence. Frequency-gated terms ("effectively", "directly") fire above a per-document occurrence threshold held in code config. Needs a scoped exception path for quoted JD text and company names; exceptions escalate rather than resolving in-model. |
| T-3.3a | nominate_banned_term_misuse_candidates | HYBRID | For frequency-gated terms below the threshold: whether the use is imprecise where more direct language would serve. The counter nominates every occurrence cheaply; judgment rules on each. Separated from T-3.3 because a frequency counter cannot assess precision, and a hard ban on ordinary English produces false positives on every draft. |
| T-3.4 | check_user_defined_terms | TOOL | Same engine, second list. No separate design. |
| T-3.5 | check_vague_metrics | TOOL | Quantifier lexicon plus absence of an adjacent numeral. Higher precision than it looks, and it fires constantly. |
| T-3.6 | check_uniform_sentence_cadence | TOOL | Variance of sentence length and structure across a run is a computed statistic. This is a strong TOOL call that reads like judgment. |
| T-3.7 | check_colon_then_gerund | TOOL | High-precision syntactic pattern. |
| T-3.8 | check_numerals_not_spelled_out | TOOL | Regex. Also the outstanding Sequence 1 bug, which is evidence it should never have depended on a model. |
| T-3.9 | check_not_just_x_but_y | HYBRID | Literal form is a regex; paraphrased variants are not. Tool catches the cheap majority, model sweeps the rest. |
| T-4.1 | check_no_tables_or_columns | TOOL | XML inspection. |
| T-4.10 | check_plain_text_roundtrip | TOOL | Runs in the Team Lead pass per v0.9, not Phase 4. Extract from the produced docx, verify no scrambling, merged sections, or dropped fields. Deterministic round trip. A failure is Critical severity, not advisory. |
| T-4.11 | estimate_page_count | TOOL | **The model cannot count pages.** Requires render-then-measure. Estimating from character count is how a resume lands at 1.4 pages. |
| T-4.12 | estimate_remaining_page_space | TOOL | Measured on the render. Feeds T-8.16. |
| T-4.13 | check_filename_pattern | TOOL | Decided 2026-07-23. Tailored output: `[Last]_[First]_Resume_[Company]_[RoleAbbrev]_[Version].docx` and the matching CoverLetter form. Company and role abbreviation are both required, since multiple roles at one company would otherwise collide. Version increments on regeneration rather than overwriting, sourced from package state in the profile file. No date on tailored files. Foundational: `[Last]_[First]_Resume_Foundational_[Date].docx`, with a version suffix only when several are produced the same day. Renamed from "Master" 2026-07-28 (beta tester feedback, see spec changelog); supersedes v0.4's `[Date]_[Version]` pattern. |
| T-4.14 | check_contact_fields | TOOL | Exactly four pipe-delimited fields in fixed order: email, phone, location, LinkedIn. Blank-but-present when unavailable, so a missing field cannot shift the fields after it. |
| T-4.2 | check_no_graphics_or_special_heading_chars | TOOL | XML inspection. |
| T-4.3 | check_contact_not_in_header_footer | TOOL | XML inspection. |
| T-4.4 | check_font_compliance | TOOL | Inspectable. |
| T-4.5 | check_date_format | TOOL | EARS ubiquitous. Regex validator, no "Present", no year-only. |
| T-4.6 | check_ongoing_role_date_substitution | TOOL | System clock. A model writing today's date from memory is a defect. |
| T-4.7 | check_section_header | TOOL | Allowlist. |
| T-4.8 | render_resume_docx | TOOL |  |
| T-4.9 | check_physical_formatting | TOOL |  |
| T-6.1 | ingest_job_description | TOOL |  |
| T-6.10 | replace_internal_names | TOOL | Same registry as T-3.15. |
| T-6.12 | check_no_invention | GATE | Every span in generated output carries a fact id. Spans with no id, or ids not in the registry, fail the gate. Provenance-based rather than heuristic, contingent on the generation step emitting ids. See section 16. |
| T-6.14 | check_unresolved_markers | GATE | No document ships with a bracketed marker in it. Trivial and absolute. |
| T-6.15 | get_fit_check_gaps_for_cover_letter | TOOL | State handoff. |
| T-6.6 | check_summary_bullet_count | TOOL | Content is judgment; bullet count is a counter. |
| T-6.7 | check_headline_title_match | TOOL | Skill selection is judgment. Exact-title match and registry membership are both mechanical, and both should hard-fail. |
| T-6.8 | check_jd_phrase_coverage | TOOL | EARS event-driven. Pure string diff. Output is an informational list. |
| T-6.9 | check_no_unauthorized_phrase_insertion | GATE | The decision is already locked. It belongs in code precisely so the model cannot talk itself into inserting one under matching pressure. |
| T-7.1 | check_cover_letter_paragraph_count | TOOL | Count. |
| T-7.12 | check_portfolio_requested | TOOL | Tool flags that the JD requests a portfolio; model writes the honest treatment. Generalizes cleanly: any user under an IP restriction hits this. Keep in V1. |
| T-7.14 | check_user_authored_text | TOOL | Text the user writes or overrides is tagged as user-authored. Language and formatting checks still run against it, findings surface as advisory, and nothing gates on them. Iris never rewrites user-authored text. Provenance: user-authored spans carry no registry fact id and are exempt from T-6.12, which would otherwise fail them for having no antecedent. |
| T-7.2 | check_cover_letter_word_count | TOOL | Count plus render measurement. |
| T-7.3 | check_closing_line_present | TOOL | Amended 2026-07-24: no longer a locked string. Iris supplies the default wording on every letter and verifies that a closing line is present and non-empty. Equality checking is dropped, since the user may edit or replace it. A replacement is user-authored text under T-7.14. |
| T-7.4 | check_salutation | GATE | The ban on "To Whom It May Concern" is a gate. Validating the salutation against four allowed shapes is a tool. Choosing which tier of the fallback hierarchy applies depends on what is known about the contact, which is judgment. |
| T-7.5 | check_cover_letter_font_matches_resume | TOOL | Left-aligned, single-spaced, 1-inch margins, blank-line breaks, font matching the paired resume. |
| T-7.9 | route_cover_letter_artifact_type | TOOL | Presence of a JD is a boolean. |
| T-8.10 | check_locked_fact_scope | TOOL | Presence check driven by `co_occurs_with`. If a fact declaring a co-occurrence partner appears and the partner does not, the check fails. Was JUDGMENT; the data model absorbs it. This is the check that failed on four resumes at once. |
| T-8.12 | check_em_dash_in_docx | TOOL |  |
| T-8.13 | check_illegal_characters | TOOL |  |
| T-8.14 | run_ai_writing_detection_signals | TOOL | Detectors produce signals; the reviewer weighs them. |
| T-8.15 | check_full_ats_scan | TOOL |  |
| T-8.16 | enumerate_unused_foundational_bullets | TOOL | Tool reports unused space and enumerates every unused foundational-resume bullet across every role. Choosing what to pull in is judgment. The enumeration must be exhaustive in code, because "checked against every bullet, not a glance" is exactly what a model does not reliably do. |
| T-8.17 | check_tl_run_on_and_jargon | HYBRID | Nominated by T-3.13 and T-3.16, weighed here. |
| T-8.19 | record_fix_attempt | TOOL | Fingerprint the finding, count attempts, escalate at two. State machine, not judgment. |
| T-8.2 | check_value_against_registry | TOOL | EARS unwanted-behavior, and the v0.3 FORGE Critical. An altered value is Critical even when it sounds plausible, which is precisely why a model cannot be the check: a model reading a plausible wrong figure accepts it. Values are per-user registry contents, not spec content. |
| T-8.20 | check_results_have_explicit_verdict | GATE | The strongest rule in v0.4 and the one that most directly encodes this pivot. A check with no underlying scan cannot clear Critical or Pedantic. |
| T-8.21 | record_limit_override | TOOL | Records which limit was exceeded, on which artifact, with the user's stated rationale, into package state in the profile. Without the record an authorization is indistinguishable from an unnoticed violation. |
| T-8.3 | nominate_added_clauses | HYBRID | Diff tailored against the foundational resume, isolate added spans, check each against the registry with full rigor. The diff is code; the check is judgment. Failure pattern (a). |
| T-8.5 | check_missing_required_sections | TOOL | Checks the output-required flag for the artifact type, per T-0.6. The predicate is now defined; this Critical-severity gate previously had no specified input. |
| T-8.6 | check_full_slop_scan | TOOL | v0.4 already specifies this tier as a programmatic scan. |
| T-8.7 | check_bullet_word_limit | TOOL | EARS state-driven. Counter. Amended 2026-07-24: 60 is a research-grounded default rather than a fixed ceiling. Over-limit bullets flag and require per-instance authorization recorded by T-8.21, not a configuration change. Supersedes the 2026-07-23 fixed-limit decision while preserving its reasoning: an authorization does not raise the ceiling for any other bullet. |
| T-8.8 | check_figure_consistency | TOOL | Extract every numeral with its context, cluster by referent, flag divergence. Catches "150 managers" appearing three times with two different values inside one document. Deterministic and cheap. |
| T-8.9 | check_figures_against_foundational | TOOL | Extraction plus comparison. |
| T-9.14 | get_todays_date | TOOL |  |
| T-9.15 | run_batch_checks | TOOL |  |
| T-9.16 | advance_phase | GATE | Added 2026-07-28. Phase advancement as a tool the model must invoke, with the transition gates enforced deterministically inside dispatch. Exists because those gates lived only in `POST /advance-phase`, which `static/app.js` never calls, so every session stayed in STARTING_POINT and T-1.8 and T-5.2 never fired once in production. The model knows when a phase's work is done, which is judgment; the harness decides whether the advance is permitted, which is not. Refuses with a finding rather than raising, so a blocked advance is recoverable by doing the missing work. |
| T-9.2 | get_inventory_section_facts | TOOL | One tool call per section beats every section in every request. |
| T-9.4 | generate_amendment_diff | TOOL |  |
| T-9.7 | check_batch_state | TOOL |  |
| T-9.8 | lock_package_version | TOOL | V1.5 in v0.4. Once a package is marked submitted, its version is frozen and regeneration produces the next version rather than overwriting. State lives in the profile file per T-2.14. |
| T-9.9 | generate_move_item_command | TOOL |  |
