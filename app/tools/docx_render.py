"""
T-4.8: docx render.

A minimal generator, not a design system. It exists so the checks in
this module (T-4.1 through T-4.4, T-4.9, T-4.10) have a real document
to run against, and so their tests exercise actual python-docx
behavior rather than mocks. It applies the mechanical rules the spec
states as absolute: 1-inch margins, an allowed font, no columns, no
tables. It does not make layout or content decisions, those are
JUDGMENT (T-4.15, T-4.16) and happen before this function is called.

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

from typing import List, Tuple

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt

from app.config import BODY_FONT_SIZE_RANGE

DEFAULT_FONT = "Calibri"
DEFAULT_BODY_SIZE = Pt(BODY_FONT_SIZE_RANGE[0] + 1)  # 11pt, mid-range of the 10-12pt band


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
        heading_para = doc.add_heading(heading, level=1)
        for run in heading_para.runs:
            run.font.name = font_name

        body_para = doc.add_paragraph(body)
        body_para.alignment = WD_ALIGN_PARAGRAPH.LEFT
        for run in body_para.runs:
            run.font.name = font_name
            run.font.size = DEFAULT_BODY_SIZE

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
        "decisions beyond what's given. Returns the file as base64. "
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
            "font_name": {"type": "string"},
        },
        "required": ["sections"],
    },
)
def render_resume_docx_tool(sections: list, font_name: str = DEFAULT_FONT) -> ToolResult:
    pairs = [(s["heading"], s["body"]) for s in sections]
    docx_bytes = generate_resume_docx(pairs, font_name=font_name)
    return ToolResult(passed=True, data={"docx_base64": base64.b64encode(docx_bytes).decode("ascii")})
