"""Phase 4 formatting checks and the Phase 8 bullet word-count counter."""

from __future__ import annotations

import re
from datetime import datetime

from app.config import BULLET_WORD_LIMIT_DEFAULT
from app.enforcement import EnforcementKind, ToolResult, tool

_DATE_RANGE_RE = re.compile(
    r"^(?P<start>[A-Z][a-z]{2} \d{4}) - (?P<end>[A-Z][a-z]{2} \d{4})$"
)
_YEAR_ONLY_RE = re.compile(r"^\d{4}(\s*-\s*\d{4})?$")


@tool(
    id="T-4.5",
    name="check_date_format",
    description=(
        "Validates an Experience or Projects date range against the "
        "required format: 'Mon YYYY - Mon YYYY', three-letter month "
        "abbreviations. Rejects year-only ranges and the literal word "
        "'Present'; ongoing roles must substitute the current month "
        "and year at generation time instead."
    ),
    kind=EnforcementKind.TOOL,
    input_schema={
        "type": "object",
        "properties": {
            "date_range_text": {
                "type": "string",
                "description": "The date range as it appears in the draft, e.g. 'Mar 2022 - Jul 2025'.",
            }
        },
        "required": ["date_range_text"],
    },
)
def check_date_format(date_range_text: str) -> ToolResult:
    text = date_range_text.strip()

    if "present" in text.lower():
        return ToolResult(
            passed=False,
            findings=[
                {
                    "severity": "Critical",
                    "issue": "Date range uses the word 'Present'.",
                    "fix": (
                        "Substitute the current month and year for an "
                        "ongoing role. This must happen at generation "
                        "time, not be left for the reader to infer."
                    ),
                }
            ],
        )

    if _YEAR_ONLY_RE.match(text):
        return ToolResult(
            passed=False,
            findings=[
                {
                    "severity": "Critical",
                    "issue": "Date range is year-only.",
                    "fix": "Use the full 'Mon YYYY - Mon YYYY' format.",
                }
            ],
        )

    if _DATE_RANGE_RE.match(text):
        return ToolResult(passed=True)

    return ToolResult(
        passed=False,
        findings=[
            {
                "severity": "Critical",
                "issue": f"Date range '{text}' does not match Mon YYYY - Mon YYYY.",
                "fix": "Reformat using three-letter month abbreviations, e.g. 'Mar 2022 - Jul 2025'.",
            }
        ],
    )


@tool(
    id="T-8.7",
    name="check_bullet_word_limit",
    description=(
        "Counts words in a single bullet. 60 is a research-grounded "
        "default, not a hard ceiling (spec Phase 8, T-8.21): a bullet "
        "over the limit is flagged and may ship only with a recorded, "
        "per-instance user authorization. This tool only counts and "
        "flags; it does not check for an authorization, that is a "
        "session-level lookup the harness performs separately."
    ),
    kind=EnforcementKind.TOOL,
    input_schema={
        "type": "object",
        "properties": {"bullet_text": {"type": "string"}},
        "required": ["bullet_text"],
    },
)
def check_bullet_word_limit(bullet_text: str) -> ToolResult:
    word_count = len(bullet_text.split())
    if word_count <= BULLET_WORD_LIMIT_DEFAULT:
        return ToolResult(passed=True, data={"word_count": word_count})
    return ToolResult(
        passed=False,
        data={"word_count": word_count},
        findings=[
            {
                "severity": "Low",
                "issue": f"Bullet is {word_count} words, over the default limit of {BULLET_WORD_LIMIT_DEFAULT}.",
                "fix": (
                    "Trim it, or record a per-instance authorization "
                    "(T-8.21) with a stated rationale if the length is "
                    "deliberate."
                ),
            }
        ],
    )


_CANONICAL_HEADERS = {
    "experience": {"experience", "professional experience", "work experience"},
    "education": {"education"},
    "skills": {"skills", "technical skills", "core skills", "core competencies"},
    "summary": {"summary", "professional summary"},
    "projects": {"projects"},
    "publications": {"publications"},
    "contact": {"contact"},
}
_ALL_ACCEPTED = {alias for aliases in _CANONICAL_HEADERS.values() for alias in aliases}


@tool(
    id="T-4.7",
    name="check_section_header",
    description=(
        "Checks a section header string against the allowlist of "
        "conventional resume section titles. Common synonyms are "
        "accepted (e.g. 'Professional Experience' for 'Experience'); "
        "anything outside the allowlist is flagged for review, since "
        "unconventional headers are a known ATS parsing failure point."
    ),
    kind=EnforcementKind.TOOL,
    input_schema={
        "type": "object",
        "properties": {"header_text": {"type": "string"}},
        "required": ["header_text"],
    },
)
def check_section_header(header_text: str) -> ToolResult:
    normalized = header_text.strip().lower()
    if normalized in _ALL_ACCEPTED:
        return ToolResult(passed=True)
    return ToolResult(
        passed=False,
        findings=[
            {
                "severity": "Medium",
                "issue": f"'{header_text}' is not a recognized conventional section header.",
                "fix": (
                    "Use a standard title (Experience, Education, Skills, "
                    "Summary, Projects, Publications, Contact) or a common "
                    "synonym of one."
                ),
            }
        ],
    )


_TAILORED_RESUME_RE = re.compile(
    r"^[\w'-]+_[\w'-]+_Resume_[\w'-]+_[\w'-]+_[Vv]?\d+\.docx$"
)
_COVER_LETTER_RE = re.compile(
    r"^[\w'-]+_[\w'-]+_CoverLetter_[\w'-]+_[\w'-]+_[Vv]?\d+\.docx$"
)
_MASTER_RE = re.compile(r"^[\w'-]+_[\w'-]+_Resume_Master_\d{4}-\d{2}-\d{2}(_v?\d+)?\.docx$")


@tool(
    id="T-4.13",
    name="check_filename_pattern",
    description=(
        "Validates an output filename against the pattern for its "
        "artifact type. Tailored resume and cover letter filenames "
        "require Last, First, Company, RoleAbbrev, and Version, no "
        "date. Master filenames require a date and take a version "
        "suffix only when several are produced the same day."
    ),
    kind=EnforcementKind.TOOL,
    input_schema={
        "type": "object",
        "properties": {
            "filename": {"type": "string"},
            "artifact_type": {
                "type": "string",
                "enum": ["tailored_resume", "cover_letter", "master"],
            },
        },
        "required": ["filename", "artifact_type"],
    },
)
def check_filename_pattern(filename: str, artifact_type: str) -> ToolResult:
    pattern_by_type = {
        "tailored_resume": (_TAILORED_RESUME_RE, "[Last]_[First]_Resume_[Company]_[RoleAbbrev]_[Version].docx"),
        "cover_letter": (_COVER_LETTER_RE, "[Last]_[First]_CoverLetter_[Company]_[RoleAbbrev]_[Version].docx"),
        "master": (_MASTER_RE, "[Last]_[First]_Resume_Master_[Date] (version suffix only if several are produced the same day)"),
    }
    if artifact_type not in pattern_by_type:
        return ToolResult(
            passed=False,
            findings=[{"severity": "Critical", "issue": f"Unknown artifact_type '{artifact_type}'.", "fix": "Use tailored_resume, cover_letter, or master."}],
        )
    pattern, expected = pattern_by_type[artifact_type]
    if pattern.match(filename):
        return ToolResult(passed=True)
    return ToolResult(
        passed=False,
        findings=[
            {
                "severity": "Critical",
                "issue": f"Filename '{filename}' does not match the required pattern.",
                "fix": f"Expected shape: {expected}",
            }
        ],
    )


@tool(
    id="T-4.6",
    name="check_ongoing_role_date_substitution",
    description=(
        "For a role marked ongoing, checks that its date range's end "
        "uses the current month and year rather than the word "
        "'Present' or a stale value. Accepts an optional reference_date "
        "for deterministic testing; defaults to the real current date."
    ),
    kind=EnforcementKind.TOOL,
    input_schema={
        "type": "object",
        "properties": {
            "date_range_text": {"type": "string"},
            "is_ongoing": {"type": "boolean"},
            "reference_date": {
                "type": "string",
                "description": "Optional 'Mon YYYY' to check against instead of the real current date.",
            },
        },
        "required": ["date_range_text", "is_ongoing"],
    },
)
def check_ongoing_role_date_substitution(
    date_range_text: str, is_ongoing: bool, reference_date: str = None
) -> ToolResult:
    if not is_ongoing:
        return ToolResult(passed=True)  # this check only applies to ongoing roles

    expected = reference_date or datetime.now().strftime("%b %Y")
    match = re.match(r"^.+ - (?P<end>[A-Z][a-z]{2} \d{4})$", date_range_text.strip())
    if not match:
        return ToolResult(
            passed=False,
            findings=[
                {
                    "severity": "Critical",
                    "issue": f"Could not parse an end date from '{date_range_text}'.",
                    "fix": f"Use 'Mon YYYY - {expected}' for an ongoing role.",
                }
            ],
        )
    end = match.group("end")
    if end == expected:
        return ToolResult(passed=True)
    return ToolResult(
        passed=False,
        findings=[
            {
                "severity": "Critical",
                "issue": f"Ongoing role ends with '{end}', but the current month/year is '{expected}'.",
                "fix": f"Substitute '{expected}' for the end date.",
            }
        ],
    )


_CONTACT_FIELD_COUNT = 4
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@tool(
    id="T-4.14",
    name="check_contact_fields",
    description=(
        "Validates a pipe-delimited CONTACT string: exactly four fields "
        "in order (email, phone, location, LinkedIn). Email, phone, and "
        "location must be non-empty; location must not look like a "
        "street address. LinkedIn may be blank. Blank-but-present is "
        "the rendering rule; it does not satisfy a required field."
    ),
    kind=EnforcementKind.TOOL,
    input_schema={
        "type": "object",
        "properties": {"contact_text": {"type": "string", "description": "e.g. 'j@x.com|555-0100|Buffalo, NY|'"}},
        "required": ["contact_text"],
    },
)
def check_contact_fields(contact_text: str) -> ToolResult:
    fields = contact_text.split("|")
    findings = []

    if len(fields) != _CONTACT_FIELD_COUNT:
        return ToolResult(
            passed=False,
            findings=[
                {
                    "severity": "Critical",
                    "issue": f"CONTACT has {len(fields)} pipe-delimited field(s), expected exactly {_CONTACT_FIELD_COUNT}.",
                    "fix": "Use email|phone|location|linkedin, blank-but-present for any missing optional value.",
                }
            ],
        )

    email, phone, location, linkedin = (f.strip() for f in fields)

    if not email or not _EMAIL_RE.match(email):
        findings.append({"severity": "Critical", "issue": f"Email field '{email}' is missing or malformed.", "fix": "Supply a valid email address."})
    if not phone:
        findings.append({"severity": "Critical", "issue": "Phone field is empty.", "fix": "Phone is required per resume best practice."})
    if not location:
        findings.append({"severity": "Critical", "issue": "Location field is empty.", "fix": "Supply city and state."})
    elif re.search(r"\d{2,}\s+\w+\s+(st|street|ave|avenue|rd|road|dr|drive|ln|lane|blvd)\b", location, re.IGNORECASE):
        findings.append({"severity": "High", "issue": f"Location '{location}' looks like a street address.", "fix": "Use city and state granularity only, never a street address."})
    # linkedin is optional; blank is fine and not flagged.

    return ToolResult(passed=len(findings) == 0, findings=findings)
