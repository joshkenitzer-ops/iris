"""
Phase 8 Final Review tools that don't belong to docx_checks.py because
they operate on plain text and session state rather than a rendered
file.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import List, Optional

from app.enforcement import EnforcementKind, ToolResult, tool
from app.session import Session
from app.tools.security import check_confidential_term_leak
from app.tools.slop import check_banned_vocabulary, check_em_dash, check_user_defined_terms, check_vague_metrics
from app.tools.slop_advanced import (
    check_colon_then_gerund,
    check_first_use_explainer,
    check_not_just_x_but_y,
    check_numerals_not_spelled_out,
    check_parallel_pair_endings,
    check_passive_weak_hedges,
    check_run_on_sentences,
    check_triple_parallel_noun_phrases,
    check_uniform_sentence_cadence,
)


@tool(
    id="T-8.6",
    name="check_full_slop_scan",
    description=(
        "Runs every Phase 3 slop check against a document in one call "
        "and aggregates every finding. This is the check the spec "
        "already frames as a programmatic scan; the Pedantic pass "
        "calls this rather than re-implementing each check."
    ),
    kind=EnforcementKind.TOOL,
    input_schema={
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "user_terms": {"type": "array", "items": {"type": "string"}},
            "confidential_terms": {"type": "array", "items": {"type": "string"}},
            "known_explainer_terms": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["text"],
    },
)
def check_full_slop_scan(
    text: str,
    user_terms: Optional[List[str]] = None,
    confidential_terms: Optional[List[str]] = None,
    known_explainer_terms: Optional[List[str]] = None,
) -> ToolResult:
    sub_results = [
        check_em_dash(text),
        check_banned_vocabulary(text),
        check_user_defined_terms(text, user_terms or []),
        check_vague_metrics(text),
        check_uniform_sentence_cadence(text),
        check_colon_then_gerund(text),
        check_numerals_not_spelled_out(text),
        check_not_just_x_but_y(text),
        check_triple_parallel_noun_phrases(text),
        check_passive_weak_hedges(text),
        check_parallel_pair_endings(text),
        check_run_on_sentences(text),
        check_confidential_term_leak(text, confidential_terms or []),
        check_first_use_explainer(text, known_explainer_terms or []),
    ]
    all_findings = [f for r in sub_results for f in r.findings]
    return ToolResult(passed=all(r.passed for r in sub_results), findings=all_findings)


@tool(
    id="T-8.10",
    name="check_locked_fact_scope",
    description=(
        "For every active registry fact that declares co_occurs_with "
        "partners, checks that if the fact's value appears in the "
        "text, its declared partners' values appear too. Catches a "
        "locked stat silently dropped from a bullet where its context "
        "still appears, the failure mode a value-match tool alone "
        "cannot see because there's nothing wrong to match against."
    ),
    kind=EnforcementKind.TOOL,
    input_schema={
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    },
    needs_session=True,
)
def check_locked_fact_scope(text: str, session: Session) -> ToolResult:
    findings = []
    lowered = text.lower()
    for fact in session.active_facts():
        if not fact.co_occurs_with:
            continue
        fact_present = fact.value.lower() in lowered or any(v.lower() in lowered for v in fact.variants)
        if not fact_present:
            continue
        for partner_id in fact.co_occurs_with:
            partner = session.registry.get(partner_id)
            if partner is None or partner.status != "active":
                continue
            partner_present = partner.value.lower() in lowered or any(v.lower() in lowered for v in partner.variants)
            if not partner_present:
                findings.append(
                    {
                        "severity": "High",
                        "issue": f"Fact '{fact.id}' appears in the text but its co-occurring partner '{partner.id}' does not.",
                        "fix": f"Include '{partner.value}' wherever '{fact.value}' appears, per the registry's co_occurs_with declaration.",
                    }
                )
    return ToolResult(passed=len(findings) == 0, findings=findings)


@tool(
    id="T-8.16",
    name="enumerate_unused_foundational_bullets",
    description=(
        "Exhaustively lists every foundational-resume bullet id not "
        "present in the tailored document. Exhaustive by construction, "
        "a set difference, rather than a sampled glance, since the spec "
        "specifically calls out 'checked against every bullet, not a "
        "glance' as something a model does not reliably do on its "
        "own. Choosing what to pull in from this list is judgment "
        "this tool does not attempt."
    ),
    kind=EnforcementKind.TOOL,
    input_schema={
        "type": "object",
        "properties": {
            "foundational_bullet_ids": {"type": "array", "items": {"type": "string"}},
            "used_bullet_ids": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["foundational_bullet_ids", "used_bullet_ids"],
    },
)
def enumerate_unused_foundational_bullets(foundational_bullet_ids: List[str], used_bullet_ids: List[str]) -> ToolResult:
    unused = sorted(set(foundational_bullet_ids) - set(used_bullet_ids))
    return ToolResult(passed=True, data={"unused_bullet_ids": unused, "unused_count": len(unused)})


@tool(
    id="T-8.19",
    name="record_fix_attempt",
    description=(
        "Increments the fix-attempt counter for a finding, keyed by "
        "content signature. Escalates rather than trying a second "
        "automated fix once the count reaches 2, per the rule that a "
        "repeat Critical is surfaced to the user, not retried."
    ),
    kind=EnforcementKind.TOOL,
    input_schema={
        "type": "object",
        "properties": {"content_signature": {"type": "string"}},
        "required": ["content_signature"],
    },
    needs_session=True,
)
def record_fix_attempt(content_signature: str, session: Session) -> ToolResult:
    count = session.fix_attempts.get(content_signature, 0) + 1
    session.fix_attempts[content_signature] = count
    escalate = count >= 2
    findings = (
        [
            {
                "severity": "High",
                "issue": f"Finding {content_signature} has now failed {count} fix attempts.",
                "fix": "Surface to the user rather than attempting another automated fix.",
            }
        ]
        if escalate
        else []
    )
    return ToolResult(passed=not escalate, findings=findings, data={"attempt_count": count, "escalate": escalate})


@tool(
    id="T-8.3",
    name="nominate_added_clauses",
    description=(
        "Diffs tailored text against the foundational resume and "
        "isolates spans present only in the tailored version, "
        "explanatory or clarifying clauses added during tailoring. "
        "Nominates each for the same registry rigor as an original "
        "claim, since added text is where an unsupported claim most "
        "often enters unnoticed."
    ),
    kind=EnforcementKind.HYBRID,
    input_schema={
        "type": "object",
        "properties": {
            "foundational_text": {"type": "string"},
            "tailored_text": {"type": "string"},
        },
        "required": ["foundational_text", "tailored_text"],
    },
)
def nominate_added_clauses(foundational_text: str, tailored_text: str) -> ToolResult:
    import difflib

    foundational_words = foundational_text.split()
    tailored_words = tailored_text.split()
    matcher = difflib.SequenceMatcher(None, foundational_words, tailored_words)

    added_spans = []
    for tag, _, _, j1, j2 in matcher.get_opcodes():
        if tag in ("insert", "replace") and j2 > j1:
            added_spans.append(" ".join(tailored_words[j1:j2]))

    findings = [
        {
            "severity": "Medium",
            "issue": f"Added clause not present in the foundational resume: '{span}'.",
            "fix": "Check this span against the registry with full rigor before it ships.",
        }
        for span in added_spans
    ]
    return ToolResult(passed=len(added_spans) == 0, findings=findings, data={"added_spans": added_spans})


@tool(
    id="T-8.17",
    name="check_tl_run_on_and_jargon",
    description=(
        "Combines the run-on sentence nominator (T-3.13) and the "
        "first-use explainer nominator (T-3.16) into the single "
        "candidate set the Team Lead pass reviews, per v0.9's decision "
        "to fold both into that pass rather than treat them as "
        "separate mechanical gates."
    ),
    kind=EnforcementKind.HYBRID,
    input_schema={
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "known_terms": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["text"],
    },
)
def check_tl_run_on_and_jargon(text: str, known_terms: Optional[List[str]] = None) -> ToolResult:
    from app.tools.slop_advanced import check_first_use_explainer, check_run_on_sentences

    run_on_result = check_run_on_sentences(text)
    jargon_result = check_first_use_explainer(text, known_terms or [])
    combined_findings = run_on_result.findings + jargon_result.findings
    return ToolResult(passed=run_on_result.passed and jargon_result.passed, findings=combined_findings)


@tool(
    id="T-8.14",
    name="run_ai_writing_detection_signals",
    description=(
        "Computes deterministic AI-writing signals for the reviewer to "
        "weigh (T-8.11): sentence-length mean and variance (low "
        "variance reads as machine-uniform, same statistic as T-3.6), "
        "lexical diversity (type-token ratio; low diversity reads as "
        "templated), and repeated sentence openers. Produces signals "
        "only, never a verdict. A model asserting 'AI-written' or "
        "'human-written' from these numbers alone, with no reviewer "
        "judgment on top, is not what this check licenses."
    ),
    kind=EnforcementKind.TOOL,
    input_schema={
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    },
)
def run_ai_writing_detection_signals(text: str) -> ToolResult:
    sentence_split_re = re.compile(r"(?<=[.!?])\s+")
    sentences = [s.strip() for s in sentence_split_re.split(text) if s.strip()]
    if not sentences:
        return ToolResult(passed=True, data={"signals": {}})

    lengths = [len(s.split()) for s in sentences]
    mean_len = sum(lengths) / len(lengths)
    variance = sum((length - mean_len) ** 2 for length in lengths) / len(lengths) if len(lengths) > 1 else 0.0

    words = re.findall(r"[A-Za-z']+", text.lower())
    diversity = len(set(words)) / len(words) if words else 0.0

    openers = [s.split()[0].lower() for s in sentences if s.split()]
    opener_counts = Counter(openers)
    repeated_openers = {word: count for word, count in opener_counts.items() if count > 1}

    signals = {
        "sentence_count": len(sentences),
        "mean_sentence_length": round(mean_len, 2),
        "sentence_length_variance": round(variance, 2),
        "lexical_diversity": round(diversity, 3),
        "repeated_openers": repeated_openers,
    }

    findings = []
    worth_a_look = len(sentences) >= 4 and variance < 4.0 and diversity < 0.5
    if worth_a_look:
        findings.append(
            {
                "severity": "Low",
                "issue": (
                    "Low sentence-length variance and low lexical diversity: "
                    "signals worth a closer reviewer look (T-8.11), not a "
                    "verdict on their own."
                ),
                "fix": "Weigh alongside voice and argument-strength judgment; these numbers alone never gate.",
            }
        )

    return ToolResult(passed=True, data={"signals": signals}, findings=findings)


@tool(
    id="T-8.20",
    name="check_results_have_explicit_verdict",
    description=(
        "Checks that a batch of check results each carry an explicit "
        "'passed' boolean rather than being inferred or assumed. "
        "Operationalizes the spec's strongest rule at the data level: "
        "a check with no underlying scan, meaning no explicit result "
        "at all, can never clear Critical or Pedantic."
    ),
    kind=EnforcementKind.GATE,
    input_schema={
        "type": "object",
        "properties": {
            "results": {
                "type": "array",
                "items": {"type": "object"},
            }
        },
        "required": ["results"],
    },
    blocking=True,
)
def check_results_have_explicit_verdict(results: List[dict]) -> ToolResult:
    missing = [i for i, r in enumerate(results) if "passed" not in r or not isinstance(r["passed"], bool)]
    findings = [
        {
            "severity": "Critical",
            "issue": f"Result at index {i} has no explicit boolean 'passed' verdict.",
            "fix": "Every check must emit a real pass/fail; a model's assertion without a scan is not sufficient.",
        }
        for i in missing
    ]
    return ToolResult(passed=len(missing) == 0, findings=findings)
