"""
T-4.8: docx render.

Applies the mechanical rules the spec states as absolute: 1-inch
margins, an allowed font, no columns, no tables. It does not make
layout or content decisions, those are JUDGMENT (T-4.15, T-4.16) and
happen before this function is called.

Section content arrives as free text per (heading, body) pair (the
tool's input schema, unchanged). Structure within that text is
recovered here rather than carried as separate fields, since the
locked careerInventory order (spec 5.9) already fixes what each
heading means:

- NAME / HEADLINE / CONTACT render as the resume's letterhead block
  (centered), not as visible section headings.
- SUMMARY / SKILLS / EXPERIENCE / PROJECTS bodies are one line per
  bullet. A bold-lead bullet ("Label: rest", spec 3.1) renders with
  the label bold, matching the check_bold_lead_structure (T-2.2)
  convention already enforced earlier in the pipeline. Within
  EXPERIENCE/PROJECTS, a line shaped like "Title | Org | Mon YYYY -
  Mon YYYY" (matching T-4.5's date format) renders as a bold role
  header instead of a bullet, and the line immediately following it
  is treated as the 1-2 sentence role summary (spec 3.1) if it is not
  itself bullet-shaped.
- Any other heading (EDUCATION, PUBLICATIONS, or a cover letter's
  prose body) renders as blank-line-separated paragraphs, no bullets,
  no bold-lead parsing, since prose sentences may contain colons that
  are not bold-lead labels.

Deliberately out of scope here: page count (T-4.11) and remaining
page-space measurement (T-4.12). Neither is obtainable from
python-docx alone, it does not perform layout, a real page count
needs an actual rendering engine (LibreOffice headless, or a
Word-compatible conversion service) sitting between this generator
and the final check. That is an infrastructure decision, not a
missing function, and it is called out rather than faked with a
character-count estimate, which is exactly the shortcut the spec
warns against.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor

from app.config import BODY_FONT_SIZE_RANGE
from app.session import Session

DEFAULT_FONT = "Calibri"
DEFAULT_BODY_SIZE = Pt(BODY_FONT_SIZE_RANGE[0] + 1)  # 11pt, mid-range of the 10-12pt band

ACCENT_COLOR = RGBColor(0x1F, 0x4E, 0x79)
MUTED_COLOR = RGBColor(0x59, 0x59, 0x59)

_HEADER_BLOCK_HEADINGS = {"NAME", "HEADLINE", "CONTACT"}
_BULLET_SECTION_HEADINGS = {"SUMMARY", "SKILLS", "EXPERIENCE", "PROJECTS"}

_ROLE_HEADER_RE = re.compile(
    r"^.+\|.+\|.*[A-Z][a-z]{2} \d{4}\s*-\s*[A-Z][a-z]{2} \d{4}\s*$"
)
_BOLD_LEAD_RE = re.compile(r"^(?P<lead>[A-Z][^:]{1,60}?):\s+(?P<rest>.+)$")
_MAX_LEAD_WORDS = 8


def _set_run_font(run, font_name: str, size=None, bold=None, italic=None, color=None) -> None:
    run.font.name = font_name
    if size is not None:
        run.font.size = size
    if bold is not None:
        run.font.bold = bold
    if italic is not None:
        run.font.italic = italic
    if color is not None:
        run.font.color.rgb = color


def _add_header_line(doc, text: str, font_name: str, *, size, bold: bool, color) -> None:
    para = doc.add_paragraph()
    para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = para.add_run(text)
    _set_run_font(run, font_name, size=size, bold=bold, color=color)


def _add_contact_line(doc, contact_text: str, font_name: str) -> None:
    fields = [f.strip() for f in contact_text.split("|") if f.strip()]
    _add_header_line(doc, "  |  ".join(fields), font_name, size=Pt(9), bold=False, color=MUTED_COLOR)


def _add_section_heading(doc, text: str, font_name: str) -> None:
    para = doc.add_paragraph()
    para.paragraph_format.space_before = Pt(10)
    para.paragraph_format.space_after = Pt(4)
    run = para.add_run(text)
    _set_run_font(run, font_name, size=Pt(13), bold=True, color=ACCENT_COLOR)


def _add_bold_lead_bullet(doc, line: str, font_name: str) -> None:
    para = doc.add_paragraph(style="List Bullet")
    match = _BOLD_LEAD_RE.match(line)
    if match and len(match.group("lead").split()) <= _MAX_LEAD_WORDS:
        lead_run = para.add_run(f"{match.group('lead')}: ")
        _set_run_font(lead_run, font_name, size=DEFAULT_BODY_SIZE, bold=True)
        rest_run = para.add_run(match.group("rest"))
        _set_run_font(rest_run, font_name, size=DEFAULT_BODY_SIZE, bold=False)
    else:
        run = para.add_run(line)
        _set_run_font(run, font_name, size=DEFAULT_BODY_SIZE, bold=False)


def _add_role_header(doc, line: str, font_name: str) -> None:
    para = doc.add_paragraph()
    para.paragraph_format.space_before = Pt(8)
    para.paragraph_format.space_after = Pt(1)
    run = para.add_run(line)
    _set_run_font(run, font_name, size=DEFAULT_BODY_SIZE, bold=True)


def _add_role_summary(doc, line: str, font_name: str) -> None:
    para = doc.add_paragraph()
    para.paragraph_format.space_after = Pt(3)
    run = para.add_run(line)
    _set_run_font(run, font_name, size=DEFAULT_BODY_SIZE, italic=True, color=MUTED_COLOR)


def _add_plain_paragraph(doc, text: str, font_name: str) -> None:
    para = doc.add_paragraph(text)
    para.alignment = WD_ALIGN_PARAGRAPH.LEFT
    for run in para.runs:
        _set_run_font(run, font_name, size=DEFAULT_BODY_SIZE, bold=False)


def _render_bulleted_body(doc, heading: str, body: str, font_name: str) -> None:
    lines = [line.strip() for line in body.splitlines()]
    allow_role_headers = heading.strip().upper() in {"EXPERIENCE", "PROJECTS"}
    previous_was_role_header = False
    for line in lines:
        if not line:
            previous_was_role_header = False
            continue
        if allow_role_headers and _ROLE_HEADER_RE.match(line):
            _add_role_header(doc, line, font_name)
            previous_was_role_header = True
            continue
        if previous_was_role_header and not _BOLD_LEAD_RE.match(line):
            _add_role_summary(doc, line, font_name)
            previous_was_role_header = False
            continue
        _add_bold_lead_bullet(doc, line, font_name)
        previous_was_role_header = False


def _render_prose_body(doc, body: str, font_name: str) -> None:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    if not paragraphs:
        paragraphs = [body]
    for paragraph_text in paragraphs:
        collapsed = " ".join(line.strip() for line in paragraph_text.splitlines() if line.strip())
        _add_plain_paragraph(doc, collapsed, font_name)


def generate_resume_docx(sections: List[Tuple[str, str]], font_name: str = DEFAULT_FONT) -> bytes:
    """sections is an ordered list of (heading, body_text) pairs, in
    the locked section order the caller is responsible for supplying
    correctly; this function renders what it's given; ordering is
    T-2.8's job, not this one's."""
    doc = Document()

    section = doc.sections[0]
    section.left_margin = Inches(1)
    section.right_margin = Inches(1)
    section.top_margin = Inches(1)
    section.bottom_margin = Inches(1)

    style = doc.styles["Normal"]
    style.font.name = font_name
    style.font.size = DEFAULT_BODY_SIZE

    for heading, body in sections:
        key = heading.strip().upper()
        if key == "NAME":
            _add_header_line(doc, body, font_name, size=Pt(18), bold=True, color=ACCENT_COLOR)
        elif key == "HEADLINE":
            _add_header_line(doc, body, font_name, size=DEFAULT_BODY_SIZE, bold=True, color=ACCENT_COLOR)
        elif key == "CONTACT":
            _add_contact_line(doc, body, font_name)
        elif key in _BULLET_SECTION_HEADINGS:
            _add_section_heading(doc, heading, font_name)
            _render_bulleted_body(doc, heading, body, font_name)
        else:
            _add_section_heading(doc, heading, font_name)
            _render_prose_body(doc, body, font_name)

    buffer = _save_to_bytes(doc)
    return buffer


def _save_to_bytes(doc: Document) -> bytes:
    import io

    stream = io.BytesIO()
    doc.save(stream)
    return stream.getvalue()


# ---------------------------------------------------------------------------
# Claude-callable wrapper. generate_resume_docx above is the real
# implementation and stays plain Python so other code (tests, other
# tools) can call it directly; this registers the same function as a
# tool so the model can trigger rendering itself.
# ---------------------------------------------------------------------------

import base64

from app.enforcement import EnforcementKind, ToolResult, tool


@tool(
    id="T-4.8",
    name="render_resume_docx",
    description=(
        "Renders an ordered list of (heading, body) sections into a "
        "docx file: 1-inch margins, an allowed font, no layout "
        "decisions beyond what's given. NAME/HEADLINE/CONTACT render "
        "as a centered letterhead block. Within SUMMARY/SKILLS/"
        "EXPERIENCE/PROJECTS, put one bullet per line using the "
        "bold-lead 'Label: rest' shape (spec 3.1) for the label to "
        "render bold; in EXPERIENCE/PROJECTS a line shaped 'Title | "
        "Org | Mon YYYY - Mon YYYY' renders as a bold role header, and "
        "the line right after it (if not itself bullet-shaped) is the "
        "italic role summary. Other sections render as blank-line-"
        "separated paragraphs. Stores the file server-side and "
        "returns a file_id the user can download from the UI — the "
        "model never sends raw docx bytes to the user directly. Also "
        "requires a filename that already passed check_filename_pattern "
        "(T-4.13). "
        "Does not decide section order or content, those come from "
        "earlier phases."
    ),
    kind=EnforcementKind.TOOL,
    input_schema={
        "type": "object",
        "properties": {
            "sections": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"heading": {"type": "string"}, "body": {"type": "string"}},
                    "required": ["heading", "body"],
                },
            },
            "filename": {"type": "string", "description": "The validated output filename, e.g. Kenitzer_Joshua_Resume_Oracle_SrIDDev_V1.docx"},
            "font_name": {"type": "string"},
        },
        "required": ["sections", "filename"],
    },
    needs_session=True,
)
def render_resume_docx_tool(sections: list, filename: str, session: Session, font_name: str = DEFAULT_FONT) -> ToolResult:
    pairs = [(s["heading"], s["body"]) for s in sections]
    docx_bytes = generate_resume_docx(pairs, font_name=font_name)
    b64 = base64.b64encode(docx_bytes).decode("ascii")
    rendered = session.add_rendered_file(
        filename=filename,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        data_base64=b64,
    )
    return ToolResult(
        passed=True,
        data={"file_id": rendered.id, "filename": rendered.filename},
    )
