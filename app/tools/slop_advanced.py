"""
The remaining Phase 3 slop checks. Two absolute TOOL rules
(colon-then-gerund, numerals spelled out) plus one statistic
(uniform cadence), and six HYBRID nominators that flag candidate
spans cheaply, leaving the judgment of whether each one actually
reads as slop to a model pass. None of these gate delivery on their
own; they feed the Pedantic and Team Lead review passes.
"""

from __future__ import annotations

import re
import statistics
from typing import List

from app.enforcement import EnforcementKind, ToolResult, tool

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

# ---------------------------------------------------------------------------
# T-3.6: uniform sentence cadence
# ---------------------------------------------------------------------------

MIN_SENTENCES_FOR_CADENCE_CHECK = 3
UNIFORM_CADENCE_STDEV_THRESHOLD = 1.5


@tool(
    id="T-3.6",
    name="check_uniform_sentence_cadence",
    description=(
        "Computes the standard deviation of sentence length across the "
        "text. A run of consecutive sentences with near-identical "
        "length and structure reads as mechanical. Needs at least "
        "three sentences to say anything meaningful."
    ),
    kind=EnforcementKind.TOOL,
    input_schema={
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    },
)
def check_uniform_sentence_cadence(text: str) -> ToolResult:
    sentences = [s for s in _SENTENCE_SPLIT_RE.split(text.strip()) if s.strip()]
    if len(sentences) < MIN_SENTENCES_FOR_CADENCE_CHECK:
        return ToolResult(passed=True, data={"sentence_count": len(sentences)})

    lengths = [len(s.split()) for s in sentences]
    stdev = statistics.stdev(lengths)
    if stdev >= UNIFORM_CADENCE_STDEV_THRESHOLD:
        return ToolResult(passed=True, data={"stdev": round(stdev, 2), "lengths": lengths})
    return ToolResult(
        passed=False,
        data={"stdev": round(stdev, 2), "lengths": lengths},
        findings=[
            {
                "severity": "Low",
                "issue": f"Sentence lengths are unusually uniform (stdev {stdev:.2f} words).",
                "fix": "Vary sentence length and structure; a mechanical cadence reads as generated.",
            }
        ],
    )


# ---------------------------------------------------------------------------
# T-3.7: colon-then-gerund
# ---------------------------------------------------------------------------

_COLON_GERUND_RE = re.compile(r"\w+:\s+[A-Za-z]+ing\b")


@tool(
    id="T-3.7",
    name="check_colon_then_gerund",
    description="Flags the 'Label: Verbing...' construction (e.g. 'Result: Increasing efficiency'), a high-precision AI-writing tell.",
    kind=EnforcementKind.TOOL,
    input_schema={
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    },
)
def check_colon_then_gerund(text: str) -> ToolResult:
    matches = _COLON_GERUND_RE.findall(text)
    findings = [
        {"severity": "Low", "issue": f"Colon-then-gerund construction found: '{m}'.", "fix": "Rewrite without the colon-lead gerund pattern."}
        for m in matches
    ]
    return ToolResult(passed=len(matches) == 0, findings=findings)


# ---------------------------------------------------------------------------
# T-3.8: numerals not spelled out
# ---------------------------------------------------------------------------

_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100,
    "thousand": 1000,
}
_NUMBER_WORD_RE = re.compile(
    r"\b(" + "|".join(sorted(_NUMBER_WORDS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)


@tool(
    id="T-3.8",
    name="check_numerals_not_spelled_out",
    description="Flags spelled-out number words. Numbers always appear as numerals, never spelled out, no exceptions.",
    kind=EnforcementKind.TOOL,
    input_schema={
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    },
)
def check_numerals_not_spelled_out(text: str) -> ToolResult:
    matches = sorted({m.lower() for m in _NUMBER_WORD_RE.findall(text)})
    findings = [
        {"severity": "Low", "issue": f"Spelled-out number '{word}' found.", "fix": f"Use the numeral {_NUMBER_WORDS[word]} instead."}
        for word in matches
    ]
    return ToolResult(passed=len(matches) == 0, findings=findings, data={"spelled_out_numbers": matches})


# ---------------------------------------------------------------------------
# T-3.9 through T-3.13, T-3.16: HYBRID nominators
# ---------------------------------------------------------------------------

_NOT_JUST_RE = re.compile(r"\bnot just\b.{0,60}?\bbut\b", re.IGNORECASE | re.DOTALL)


@tool(
    id="T-3.9",
    name="check_not_just_x_but_y",
    description="Nominates the literal 'not just X but Y' formula. Catches the exact phrasing; paraphrased variants need a model sweep.",
    kind=EnforcementKind.HYBRID,
    input_schema={
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    },
)
def check_not_just_x_but_y(text: str) -> ToolResult:
    matches = _NOT_JUST_RE.findall(text)
    findings = [{"severity": "Low", "issue": "Literal 'not just X but Y' formula found.", "fix": "Rewrite directly; state the stronger claim without the formula."} for _ in matches]
    return ToolResult(passed=len(matches) == 0, findings=findings)


_TRIPLE_PARALLEL_RE = re.compile(r"\b(\w+(?:\s\w+){0,2}),\s(\w+(?:\s\w+){0,2}),?\sand\s(\w+(?:\s\w+){0,2})\b")


@tool(
    id="T-3.10",
    name="check_triple_parallel_noun_phrases",
    description="Nominates 'X, Y, and Z' three-item list constructions. Cheap detection; whether it reads as slop or accurate enumeration is a model judgment.",
    kind=EnforcementKind.HYBRID,
    input_schema={
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    },
)
def check_triple_parallel_noun_phrases(text: str) -> ToolResult:
    matches = _TRIPLE_PARALLEL_RE.findall(text)
    findings = [
        {"severity": "Low", "issue": f"Triple parallel phrase: '{a}, {b}, and {c}'.", "fix": "Confirm this reads as substantive enumeration, not filler."}
        for a, b, c in matches
    ]
    return ToolResult(passed=len(matches) == 0, findings=findings)


_WEAK_HEDGE_PHRASES = ["participated in", "assisted with", "was involved in", "contributed to", "helped with"]
_PASSIVE_RE = re.compile(r"\b(was|were|been|being|is|are)\s+\w+ed\b", re.IGNORECASE)


@tool(
    id="T-3.11",
    name="check_passive_weak_hedges",
    description="Nominates known weak-hedge phrases and generic passive-voice constructions. Whether the passive weakens the specific claim is a model judgment.",
    kind=EnforcementKind.HYBRID,
    input_schema={
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    },
)
def check_passive_weak_hedges(text: str) -> ToolResult:
    lowered = text.lower()
    findings = []
    for phrase in _WEAK_HEDGE_PHRASES:
        if phrase in lowered:
            findings.append({"severity": "Low", "issue": f"Weak hedge phrase '{phrase}' found.", "fix": "State the specific action and result directly."})
    for match in _PASSIVE_RE.finditer(text):
        findings.append({"severity": "Low", "issue": f"Passive construction: '{match.group(0)}'.", "fix": "Confirm whether an active rewrite would state the claim more directly."})
    return ToolResult(passed=len(findings) == 0, findings=findings)


@tool(
    id="T-3.12",
    name="check_parallel_pair_endings",
    description="Nominates consecutive sentences ending on the same word or the same -ing/-ed suffix, a structural repetition tell.",
    kind=EnforcementKind.HYBRID,
    input_schema={
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    },
)
def check_parallel_pair_endings(text: str) -> ToolResult:
    sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(text.strip()) if s.strip()]
    findings = []
    for i in range(len(sentences) - 1):
        last_a = sentences[i].rstrip(".!?").split()[-1].lower() if sentences[i].split() else ""
        last_b = sentences[i + 1].rstrip(".!?").split()[-1].lower() if sentences[i + 1].split() else ""
        if not last_a or not last_b:
            continue
        same_word = last_a == last_b
        same_suffix = len(last_a) > 3 and len(last_b) > 3 and last_a[-3:] == last_b[-3:] and last_a[-3:] in ("ing", "ed.")
        if same_word or (last_a.endswith("ing") and last_b.endswith("ing")) or (last_a.endswith("ed") and last_b.endswith("ed")):
            findings.append(
                {
                    "severity": "Low",
                    "issue": f"Consecutive sentences both end on '{last_a}' / '{last_b}'.",
                    "fix": "Vary sentence endings; a repeated structural beat reads as generated.",
                }
            )
    return ToolResult(passed=len(findings) == 0, findings=findings)


RUN_ON_WORD_THRESHOLD = 30
RUN_ON_CONJUNCTION_THRESHOLD = 3
_CONJUNCTIONS = {"and", "but", "so", "which", "that", "while", "because"}


@tool(
    id="T-3.13",
    name="check_run_on_sentences",
    description="Nominates sentences over 30 words or containing 3+ coordinating conjunctions. Whether it's one idea or several stitched together is a model judgment.",
    kind=EnforcementKind.HYBRID,
    input_schema={
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    },
)
def check_run_on_sentences(text: str) -> ToolResult:
    sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(text.strip()) if s.strip()]
    findings = []
    for sentence in sentences:
        words = sentence.split()
        conjunction_count = sum(1 for w in words if w.lower().strip(",.") in _CONJUNCTIONS)
        if len(words) > RUN_ON_WORD_THRESHOLD or conjunction_count >= RUN_ON_CONJUNCTION_THRESHOLD:
            findings.append(
                {
                    "severity": "Low",
                    "issue": f"Candidate run-on sentence ({len(words)} words, {conjunction_count} conjunctions): '{sentence[:60]}...'.",
                    "fix": "Confirm whether this is one idea or several that should split.",
                }
            )
    return ToolResult(passed=len(findings) == 0, findings=findings)


@tool(
    id="T-3.16",
    name="check_first_use_explainer",
    description=(
        "Nominates the first occurrence of each known term for an "
        "explainer check. Registry-listed terms are detectable "
        "mechanically; whether a given non-registry proper noun needs "
        "one is judgment (T-2.12), not attempted here."
    ),
    kind=EnforcementKind.HYBRID,
    input_schema={
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "known_terms": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["text", "known_terms"],
    },
)
def check_first_use_explainer(text: str, known_terms: List[str]) -> ToolResult:
    lowered = text.lower()
    findings = []
    for term in known_terms:
        idx = lowered.find(term.strip().lower())
        if idx == -1:
            continue
        findings.append(
            {
                "severity": "Low",
                "issue": f"First use of '{term}' found; confirm a plain-English explainer is nearby.",
                "fix": "Add a brief explainer on first use if one isn't already present.",
            }
        )
    return ToolResult(passed=len(findings) == 0, findings=findings)


@tool(
    id="T-3.3a",
    name="nominate_banned_term_misuse_candidates",
    description=(
        "Nominates every occurrence of a frequency-gated banned term "
        "('effectively', 'directly'), including uses below the "
        "frequency threshold that check_banned_vocabulary would pass. "
        "A single ordinary use might still be imprecise where more "
        "direct language would serve; that judgment belongs to a "
        "model, this only surfaces the candidates with surrounding "
        "context."
    ),
    kind=EnforcementKind.HYBRID,
    input_schema={
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    },
)
def nominate_banned_term_misuse_candidates(text: str) -> ToolResult:
    from app.tools.slop import FREQUENCY_GATED_TERMS

    candidates = []
    lowered = text.lower()
    for term in FREQUENCY_GATED_TERMS:
        start = 0
        while True:
            idx = lowered.find(term, start)
            if idx == -1:
                break
            context_start = max(0, idx - 30)
            context_end = min(len(text), idx + len(term) + 30)
            candidates.append({"term": term, "context": text[context_start:context_end]})
            start = idx + len(term)

    findings = [
        {
            "severity": "Low",
            "issue": f"Candidate for misuse review: '{c['context']}'.",
            "fix": "Confirm this use is precise; cut or rephrase if more direct language would serve.",
        }
        for c in candidates
    ]
    return ToolResult(passed=len(candidates) == 0, findings=findings, data={"candidates": candidates})


# ---------------------------------------------------------------------------
# T-3.17: Tense consistency check (HYBRID nominator)
# ---------------------------------------------------------------------------


@tool(
    id="T-3.17",
    name="nominate_tense_inconsistency_candidates",
    description=(
        "Nominates sentences in a role block that may be using the wrong "
        "tense. Completed roles should use past tense throughout; the "
        "current role should use present tense throughout. The nominator "
        "is cheap and over-inclusive: it flags any sentence containing a "
        "present-tense verb in a completed role block, or a past-tense "
        "verb in the current role block, and hands the candidates to "
        "judgment to confirm whether the shift is intentional. "
        "Args: `text` is the role block text; `is_current_role` indicates "
        "whether this is the user's current position."
    ),
    kind=EnforcementKind.HYBRID,
    input_schema={
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "is_current_role": {
                "type": "boolean",
                "description": "True if this is the user's current role (ongoing).",
            },
        },
        "required": ["text", "is_current_role"],
    },
)
def nominate_tense_inconsistency_candidates(text: str, is_current_role: bool) -> ToolResult:
    import re

    # Surface indicators only: auxiliary verbs are the cheapest signal.
    # Present-tense markers (wrong in a completed role):
    _PRESENT = re.compile(
        r"\b(am|is|are|have|has|do|does|lead|manage|build|drive|"
        r"oversee|develop|create|run|own|coordinate|support)\b",
        re.IGNORECASE,
    )
    # Past-tense markers (wrong in the current role):
    _PAST = re.compile(
        r"\b(was|were|had|did|led|managed|built|drove|oversaw|"
        r"developed|created|ran|owned|coordinated|supported)\b",
        re.IGNORECASE,
    )

    pattern = _PRESENT if not is_current_role else _PAST
    wrong_label = "present" if not is_current_role else "past"
    expected = "past" if not is_current_role else "present"

    candidates = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n", text):
        s = sentence.strip()
        if not s:
            continue
        if pattern.search(s):
            candidates.append(s)

    findings = [
        {
            "severity": "Medium",
            "issue": (
                f"Possible tense inconsistency in a "
                f"{'current' if is_current_role else 'completed'} role: "
                f"\"{c}\" contains a {wrong_label}-tense verb. "
                f"Expected {expected} tense throughout."
            ),
            "fix": "Confirm whether the tense shift is intentional. If not, rewrite in the expected tense.",
        }
        for c in candidates
    ]
    return ToolResult(
        passed=len(candidates) == 0,
        findings=findings,
        data={"candidates": candidates, "is_current_role": is_current_role},
    )


# ---------------------------------------------------------------------------
# T-3.18: Repeated sentence opener check (HYBRID nominator)
# ---------------------------------------------------------------------------


@tool(
    id="T-3.18",
    name="nominate_repeated_opener_candidates",
    description=(
        "Nominates runs of three or more consecutive sentences (or bullets) "
        "that begin with the same word or structural pattern. A repeated "
        "opener is a structural AI tell even when each sentence is otherwise "
        "clean. The nominator flags the run and hands it to judgment to "
        "confirm whether the repetition is intentional emphasis or "
        "structural laziness."
    ),
    kind=EnforcementKind.HYBRID,
    input_schema={
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    },
)
def nominate_repeated_opener_candidates(text: str) -> ToolResult:
    import re

    # Split on sentence-ending punctuation OR bullet newlines.
    sentences = [
        s.strip().lstrip("-•*·").strip()
        for s in re.split(r"(?<=[.!?])\s+|\n", text)
        if s.strip()
    ]

    def first_word(s: str) -> str:
        words = s.split()
        return words[0].lower() if words else ""

    runs = []
    i = 0
    while i < len(sentences):
        opener = first_word(sentences[i])
        if not opener:
            i += 1
            continue
        j = i + 1
        while j < len(sentences) and first_word(sentences[j]) == opener:
            j += 1
        if j - i >= 3:
            runs.append({"opener": opener, "sentences": sentences[i:j]})
        i = j if j > i else i + 1

    findings = [
        {
            "severity": "Low",
            "issue": (
                f"Repeated opener '{r['opener']}' across "
                f"{len(r['sentences'])} consecutive sentences. "
                f"First few: {r['sentences'][:3]}"
            ),
            "fix": "Vary the sentence structure or opener unless the repetition is intentional emphasis.",
        }
        for r in runs
    ]
    return ToolResult(passed=len(runs) == 0, findings=findings, data={"runs": runs})
