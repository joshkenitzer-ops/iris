import base64
import io
import unittest

from docx import Document

from app.tools.docx_render import render_resume_docx_tool


class TestRenderResumeDocxTool(unittest.TestCase):
    def test_produces_valid_docx(self) -> None:
        result = render_resume_docx_tool(sections=[{"heading": "Experience", "body": "Led the migration."}])
        self.assertTrue(result.passed)
        docx_bytes = base64.b64decode(result.data["docx_base64"])
        doc = Document(io.BytesIO(docx_bytes))
        texts = [p.text for p in doc.paragraphs if p.text.strip()]
        self.assertIn("Experience", texts)
        self.assertIn("Led the migration.", texts)

    def test_custom_font_applied(self) -> None:
        result = render_resume_docx_tool(
            sections=[{"heading": "Experience", "body": "Led the migration."}], font_name="Georgia"
        )
        docx_bytes = base64.b64decode(result.data["docx_base64"])
        doc = Document(io.BytesIO(docx_bytes))
        body_para = [p for p in doc.paragraphs if p.text == "Led the migration."][0]
        for run in body_para.runs:
            self.assertEqual(run.font.name, "Georgia")


if __name__ == "__main__":
    unittest.main()
