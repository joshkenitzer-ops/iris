"""
T-4.11 / T-4.12: page count and remaining page space, estimated from a
heuristic rather than a true render.

python-docx holds the document model but does no layout: it cannot
tell you where a page actually breaks, because that depends on a real
layout engine (Word, LibreOffice) doing font metrics, kerning, and
justification this library never touches. The honest options were:
stand up an external renderer (LibreOffice headless) and shell out to
it per document, or estimate from what the docx model already gives
us (font size, page geometry, paragraph spacing, character counts)
and accept the imprecision. Decided 2026-07-25: heuristic, not a
renderer. TAILORED_PAGE_TARGET (app.config) is already a range, not
an exact count, a resume-length judgment call doesn't need
page-perfect layout the way a paginated legal filing would, and a
renderer would mean an extra system dependency and a subprocess call
per document, for a target that was never exact in the first place.
Revisit if real resumes prove this estimate off by more than the
tolerance built into the findings below.

What this does NOT model, because the cost of modeling it doesn't
match what a resume needs: kerning and true proportional character
widths (some letters are much wider than others; char_width_factor in
app.config.PAGE_ESTIMATE is an average, not per-glyph), bold/italic
width changes, hyphenation and exact word-wrap points, widow/orphan
control, and justified-text reflow. All of these push the true page
count in either direction by a small amount; that is exactly why
estimate_page_count reports a Low finding at the target boundary
rather than a Critical one, and why estimate_remaining_page_space
never gates at all.
"""

from __future__ import annotations

import base64
import io
import math
from dataclasses import dataclass

from docx import Document

from app.config import PAGE_ESTIMATE, TAILORED_PAGE_TARGET
from app.enforcement import EnforcementKind, ToolResult, tool


def _load_document(docx_base64: str) -> Document:
    raw = base64.b64decode(docx_base64)
    return Document(io.BytesIO(raw))


def _paragraph_font_size_pt(paragraph, default_pt: float) -> float:
    """A paragraph's first run with an explicit size wins; python-docx
    returns None for a run that inherits its size from the style, so
    falling back to the configured default is the correct behavior
    for those runs, not a bug being papered over."""
    for run in paragraph.runs:
        if run.font.size is not None:
            return run.font.size.pt
    return default_pt


def _line_height_pts(paragraph, font_size_pt: float, line_height_factor: float) -> float:
    base = font_size_pt * line_height_factor
    line_spacing = paragraph.paragraph_format.line_spacing
    if line_spacing is None:
        return base
    pt_value = getattr(line_spacing, "pt", None)
    if pt_value is not None:
        return pt_value  # an absolute line height (an EXACTLY/AT_LEAST spacing rule)
    try:
        multiplier = float(line_spacing)  # a plain "N lines" multiplier
        return base * multiplier
    except (TypeError, ValueError):
        return base


def _spacing_pts(value) -> float:
    return value.pt if value is not None else 0.0


@dataclass
class _LayoutEstimate:
    total_line_equivalents: float
    lines_per_page: float
    page_count: int
    lines_remaining_on_last_page: float


def _estimate_layout(document: Document) -> _LayoutEstimate:
    cfg = PAGE_ESTIMATE
    usable_width_pts = (cfg["page_width_in"] - 2 * cfg["margin_in"]) * 72
    usable_height_pts = (cfg["page_height_in"] - 2 * cfg["margin_in"]) * 72

    total_lines = 0.0
    for paragraph in document.paragraphs:
        font_size = _paragraph_font_size_pt(paragraph, cfg["default_font_size_pt"])
        line_height = _line_height_pts(paragraph, font_size, cfg["line_height_factor"])
        char_width = font_size * cfg["char_width_factor"]
        chars_per_line = max(1.0, usable_width_pts / char_width)

        text = paragraph.text
        text_lines = max(1, math.ceil(len(text) / chars_per_line)) if text.strip() else 1

        spacing_pts = _spacing_pts(paragraph.paragraph_format.space_before) + _spacing_pts(
            paragraph.paragraph_format.space_after
        )
        spacing_lines = spacing_pts / line_height if line_height else 0.0

        total_lines += text_lines + spacing_lines

    # A single lines_per_page figure, based on the configured default
    # font size rather than a per-paragraph weighted average: body
    # text dominates a resume by line count, so this keeps the ratio's
    # units consistent without needing a true weighted layout, which
    # would be a lot of added complexity for a heuristic that is
    # already approximate by design.
    default_line_height = cfg["default_font_size_pt"] * cfg["line_height_factor"]
    lines_per_page = max(1.0, usable_height_pts / default_line_height)

    if total_lines <= 0:
        return _LayoutEstimate(0.0, lines_per_page, 0, lines_per_page)

    page_count = max(1, math.ceil(total_lines / lines_per_page))
    lines_used_on_last_page = total_lines - (page_count - 1) * lines_per_page
    lines_remaining_on_last_page = max(0.0, lines_per_page - lines_used_on_last_page)

    return _LayoutEstimate(total_lines, lines_per_page, page_count, lines_remaining_on_last_page)


@tool(
    id="T-4.11",
    name="estimate_page_count",
    description=(
        "Estimates the rendered page count of a docx from font size, "
        "page geometry, and character/line counts, since python-docx "
        "holds the document model but does no real layout. A "
        "heuristic, not a render (see this module's docstring for "
        "what it doesn't model). Reports a Low finding at the target "
        "boundary rather than a Critical one, since the estimate "
        "itself carries a margin of error TAILORED_PAGE_TARGET does "
        "not."
    ),
    kind=EnforcementKind.TOOL,
    input_schema={
        "type": "object",
        "properties": {"docx_base64": {"type": "string"}},
        "required": ["docx_base64"],
    },
)
def estimate_page_count(docx_base64: str) -> ToolResult:
    document = _load_document(docx_base64)
    layout = _estimate_layout(document)
    min_pages, max_pages = TAILORED_PAGE_TARGET

    findings = []
    if layout.page_count < min_pages or layout.page_count > max_pages:
        findings.append(
            {
                "severity": "Low",
                "issue": (
                    f"Estimated at {layout.page_count} page(s); target is "
                    f"{min_pages}-{max_pages}. This is a heuristic estimate, "
                    "not an exact render, so treat it as approximate."
                ),
                "fix": "Consider trimming or expanding toward the target; the actual rendered count may differ slightly.",
            }
        )

    return ToolResult(
        passed=len(findings) == 0,
        findings=findings,
        data={"estimated_page_count": layout.page_count, "target_range": list(TAILORED_PAGE_TARGET)},
    )


@tool(
    id="T-4.12",
    name="estimate_remaining_page_space",
    description=(
        "Estimates how much room is left on the last page, in "
        "line-equivalents and as a fraction of a page, from the same "
        "heuristic as estimate_page_count (T-4.11). Informational "
        "only: useful for a judgment call about whether one more "
        "bullet fits without spilling onto a new page. Never gates."
    ),
    kind=EnforcementKind.TOOL,
    input_schema={
        "type": "object",
        "properties": {"docx_base64": {"type": "string"}},
        "required": ["docx_base64"],
    },
)
def estimate_remaining_page_space(docx_base64: str) -> ToolResult:
    document = _load_document(docx_base64)
    layout = _estimate_layout(document)

    remaining_fraction = (
        layout.lines_remaining_on_last_page / layout.lines_per_page if layout.lines_per_page else 0.0
    )

    return ToolResult(
        passed=True,
        data={
            "estimated_lines_remaining": round(layout.lines_remaining_on_last_page, 1),
            "estimated_page_fraction_remaining": round(remaining_fraction, 2),
            "estimated_page_count": layout.page_count,
        },
    )
