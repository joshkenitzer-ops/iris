"""
T-7.4: salutation validity. HYBRID + GATE in the tool list: the ban on
"To Whom It May Concern" is a gate, validating the salutation's shape
against the four allowed forms is a tool, and choosing which tier of
the fallback applies (named contact vs department vs company team vs
generic) depends on what is actually known about the contact, which
is judgment this module does not attempt. Feed it a salutation string;
it tells you whether the shape is valid and whether the banned phrase
is present. It does not pick the salutation for you.
"""

from __future__ import annotations

import re

from app.enforcement import EnforcementKind, ToolResult, tool

_BANNED_PHRASE = "to whom it may concern"

_SHAPES = [
    re.compile(r"^Dear [A-Z][\w'.-]+(\s[A-Z][\w'.-]+)*,$"),  # "Dear Jane Smith,"
    re.compile(r"^[A-Z][\w'&-]+(\s[A-Z][\w'&-]+)* Team,$"),  # "Engineering Team,"
    re.compile(r"^[A-Z][\w'&-]+(\s[A-Z][\w'&-]+)* Recruiting Team,$"),  # "Acme Recruiting Team,"
    re.compile(r"^Dear Hiring Manager,$"),
]


@tool(
    id="T-7.4",
    name="check_salutation",
    description=(
        "Validates a cover letter salutation. 'To Whom It May Concern' "
        "is a hard gate failure, never acceptable. Otherwise checks "
        "the string against the four allowed shapes (named contact; "
        "department team; company recruiting team; 'Dear Hiring "
        "Manager,'). Does not choose which tier applies, that depends "
        "on what's known about the contact and is a judgment call made "
        "before this tool runs."
    ),
    kind=EnforcementKind.GATE,
    input_schema={
        "type": "object",
        "properties": {"salutation": {"type": "string"}},
        "required": ["salutation"],
    },
    blocking=True,
)
def check_salutation(salutation: str) -> ToolResult:
    text = salutation.strip()
    if text.lower().rstrip(",. ") == _BANNED_PHRASE:
        return ToolResult(
            passed=False,
            findings=[
                {
                    "severity": "Critical",
                    "issue": "Salutation is 'To Whom It May Concern', banned without exception.",
                    "fix": "Use a named contact, department, company recruiting team, or 'Dear Hiring Manager,'.",
                }
            ],
        )
    if any(shape.match(text) for shape in _SHAPES):
        return ToolResult(passed=True)
    return ToolResult(
        passed=False,
        findings=[
            {
                "severity": "Medium",
                "issue": f"Salutation '{text}' does not match any of the four allowed shapes.",
                "fix": "Use a named contact, a department/team form, a company recruiting team form, or 'Dear Hiring Manager,'.",
            }
        ],
    )


_PARAGRAPH_COUNT_REQUIRED = 4

# A sign-off line: "Sincerely," "Best regards," "Thank you," and so on.
# Deliberately matched as a short line ending in a comma rather than
# against a fixed vocabulary, since the closing is user-adjustable
# (T-7.3, 2026-07-24) and a fixed list would go stale.
_SIGN_OFF_RE = re.compile(r"^[A-Z][A-Za-z ]{0,24},$")
_SALUTATION_RE = re.compile(r"^.{0,60},$")


def _looks_like_a_name(line: str) -> bool:
    """A trailing bare name, with no sign-off line above it.

    Keyed on the absence of sentence-ending punctuation rather than on
    name shape: a body paragraph ends in a period, a signature does not.
    That distinguishes the two without trying to guess what counts as a
    plausible human name, which is not a judgment this should attempt."""
    stripped = line.strip()
    return (
        0 < len(stripped) <= 60
        and not stripped.endswith((".", "!", "?", ":", ";"))
        and len(stripped.split()) <= 5
    )


def _split_letter_structure(letter_text: str) -> dict:
    """Separates a cover letter into salutation, body paragraphs, and
    signature block.

    Splitting on blank lines alone and counting every block is what
    broke here: a signature sitting on its own line counted as a fifth
    paragraph, T-7.1 failed, and the model resolved the failure by
    deleting the sender's name from the letter. That shipped a cover
    letter with no signature (confirmed live 2026-07-28, caught by the
    user rather than by any check). The paragraph rule was always about
    the four BODY paragraphs, spec Phase 7: opening hook, core
    capability, company alignment carrying the gap, closing. The
    salutation and signature are structure around them, not paragraphs
    subject to the count.

    Heuristics are deliberately conservative: anything not confidently
    identified as salutation or signature stays in the body, so an
    ambiguous letter is still measured against the rule rather than
    quietly excused from it."""
    blocks = [b.strip() for b in letter_text.split("\n\n") if b.strip()]
    salutation, signature = None, None

    if blocks and _SALUTATION_RE.match(blocks[0]) and "\n" not in blocks[0]:
        salutation = blocks.pop(0)

    # A signature is the sign-off plus the name ("Sincerely,\nJoshua
    # Kenitzer"), the two split across consecutive blocks, or a bare
    # name with no sign-off at all. All three shapes appear in real
    # letters and all three were previously counted as a paragraph.
    if blocks:
        last_lines = blocks[-1].splitlines()
        if _SIGN_OFF_RE.match(last_lines[0].strip()) and len(last_lines) <= 3:
            signature = blocks.pop()
        elif len(last_lines) == 1 and len(blocks) > 1:
            prior = blocks[-2].splitlines()
            if len(prior) == 1 and _SIGN_OFF_RE.match(prior[0].strip()):
                signature = blocks.pop(-2) + "\n" + blocks.pop()
            elif _looks_like_a_name(last_lines[0]):
                signature = blocks.pop()

    return {"salutation": salutation, "body": blocks, "signature": signature}


@tool(
    id="T-7.1",
    name="check_cover_letter_paragraph_count",
    description=(
        "Checks a cover letter has exactly four BODY paragraphs, "
        "separated by blank lines. The salutation and the signature "
        "block are structure, not body paragraphs, and are excluded "
        "from the count. Do not delete or merge a signature to satisfy "
        "this check: a letter must keep the sender's name."
    ),
    kind=EnforcementKind.TOOL,
    input_schema={
        "type": "object",
        "properties": {"letter_text": {"type": "string"}},
        "required": ["letter_text"],
    },
)
def check_cover_letter_paragraph_count(letter_text: str) -> ToolResult:
    structure = _split_letter_structure(letter_text)
    count = len(structure["body"])
    data = {
        "paragraph_count": count,
        "has_salutation": structure["salutation"] is not None,
        "has_signature": structure["signature"] is not None,
    }
    if count == _PARAGRAPH_COUNT_REQUIRED:
        return ToolResult(passed=True, data=data)
    return ToolResult(
        passed=False,
        data=data,
        findings=[
            {
                "severity": "High",
                "issue": f"Cover letter has {count} body paragraph(s); exactly {_PARAGRAPH_COUNT_REQUIRED} are required.",
                "fix": (
                    "Restructure into: opening hook, core capability argument, company "
                    "alignment (carrying any gap), closing. The salutation and signature "
                    "are not counted; do not remove them to reach the number."
                ),
            }
        ],
    )


@tool(
    id="T-7.2",
    name="check_cover_letter_word_count",
    description=(
        "Checks a cover letter's word count against the default 250-400 "
        "range. A letter outside this range may ship only with a "
        "recorded per-instance authorization (T-7.13); this tool only "
        "counts and flags, it does not check for an authorization."
    ),
    kind=EnforcementKind.TOOL,
    input_schema={
        "type": "object",
        "properties": {"letter_text": {"type": "string"}},
        "required": ["letter_text"],
    },
)
def check_cover_letter_word_count(letter_text: str) -> ToolResult:
    from app.config import COVER_LETTER_WORD_RANGE

    word_count = len(letter_text.split())
    low, high = COVER_LETTER_WORD_RANGE
    if low <= word_count <= high:
        return ToolResult(passed=True, data={"word_count": word_count})
    return ToolResult(
        passed=False,
        data={"word_count": word_count},
        findings=[
            {
                "severity": "Medium",
                "issue": f"Cover letter is {word_count} words, outside the default {low}-{high} range.",
                "fix": "Trim or expand, or record a per-instance authorization (T-7.13) with a stated rationale.",
            }
        ],
    )


@tool(
    id="T-7.9",
    name="route_cover_letter_artifact_type",
    description=(
        "Routes to Letter of Interest when no job description exists, "
        "or a standard cover letter when one does. Trivial boolean "
        "routing, no judgment: presence of a JD decides it."
    ),
    kind=EnforcementKind.TOOL,
    input_schema={
        "type": "object",
        "properties": {"has_job_description": {"type": "boolean"}},
        "required": ["has_job_description"],
    },
)
def route_cover_letter_artifact_type(has_job_description: bool) -> ToolResult:
    artifact_type = "cover_letter" if has_job_description else "letter_of_interest"
    return ToolResult(passed=True, data={"artifact_type": artifact_type})


@tool(
    id="T-7.14",
    name="check_user_authored_text",
    description=(
        "Runs the standard language checks (em dash, banned "
        "vocabulary) against text the user wrote or edited directly, "
        "such as a customized closing line. Findings surface as "
        "advisory only and never gate delivery, and this tool never "
        "modifies the text. This is the exemption path T-6.12's "
        "provenance gate relies on for user-authored spans."
    ),
    kind=EnforcementKind.TOOL,
    input_schema={
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    },
)
def check_user_authored_text(text: str) -> ToolResult:
    from app.tools.slop import check_banned_vocabulary, check_em_dash

    em_dash_result = check_em_dash(text)
    vocab_result = check_banned_vocabulary(text)
    advisory_findings = em_dash_result.findings + vocab_result.findings

    # passed is always True: these findings are advisory, never gating,
    # per the rule that Iris never silently modifies or blocks
    # something the user wrote themselves.
    return ToolResult(passed=True, data={"advisory_findings": advisory_findings})


@tool(
    id="T-7.3",
    name="check_closing_line_present",
    description=(
        "Verifies a cover letter ends with a non-empty closing line. "
        "The line's exact wording is no longer locked (2026-07-24, "
        "user may adjust the default); this only checks something is "
        "there, not what it says."
    ),
    kind=EnforcementKind.TOOL,
    input_schema={
        "type": "object",
        "properties": {"letter_text": {"type": "string"}},
        "required": ["letter_text"],
    },
)
def check_closing_line_present(letter_text: str) -> ToolResult:
    stripped = letter_text.strip()
    last_line = stripped.splitlines()[-1].strip() if stripped else ""
    if last_line:
        return ToolResult(passed=True, data={"closing_line": last_line})
    return ToolResult(
        passed=False,
        findings=[{"severity": "High", "issue": "Cover letter has no closing line.", "fix": "Add a closing line before the signature."}],
    )


@tool(
    id="T-7.5",
    name="check_cover_letter_font_matches_resume",
    description="Checks the cover letter's font family matches the paired resume's font family exactly.",
    kind=EnforcementKind.TOOL,
    input_schema={
        "type": "object",
        "properties": {
            "cover_letter_font": {"type": "string"},
            "resume_font": {"type": "string"},
        },
        "required": ["cover_letter_font", "resume_font"],
    },
)
def check_cover_letter_font_matches_resume(cover_letter_font: str, resume_font: str) -> ToolResult:
    if cover_letter_font == resume_font:
        return ToolResult(passed=True)
    return ToolResult(
        passed=False,
        findings=[
            {
                "severity": "Medium",
                "issue": f"Cover letter font '{cover_letter_font}' does not match resume font '{resume_font}'.",
                "fix": "Use the same font family as the paired resume.",
            }
        ],
    )


_PORTFOLIO_KEYWORDS = ["portfolio", "work samples", "case studies", "writing samples", "design samples"]


@tool(
    id="T-7.12",
    name="check_portfolio_requested",
    description=(
        "Detects whether a job description requests a portfolio or "
        "work samples. Trigger only; the honest treatment when the "
        "user cannot supply one is a model judgment written under the "
        "IP-policy rule, not attempted here."
    ),
    kind=EnforcementKind.TOOL,
    input_schema={
        "type": "object",
        "properties": {"jd_text": {"type": "string"}},
        "required": ["jd_text"],
    },
)
def check_portfolio_requested(jd_text: str) -> ToolResult:
    lowered = jd_text.lower()
    matched = [kw for kw in _PORTFOLIO_KEYWORDS if kw in lowered]
    return ToolResult(passed=True, data={"portfolio_requested": len(matched) > 0, "matched_keywords": matched})
