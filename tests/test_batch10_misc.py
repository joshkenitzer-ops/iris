import base64
import importlib.util
import io
import unittest

from docx import Document

from app.tools.intake import ingest_document, validate_structured_intake_form

_PYPDF_AVAILABLE = importlib.util.find_spec("pypdf") is not None
_SKIP_NO_PYPDF = "pypdf is not installed; the PDF path in T-0.1 is optional by design (lazy-imported), and so is testing it."


def _docx_base64(paragraphs=None, table_rows=None) -> str:
    doc = Document()
    for text in paragraphs or []:
        doc.add_paragraph(text)
    if table_rows:
        table = doc.add_table(rows=len(table_rows), cols=len(table_rows[0]))
        for r, row_values in enumerate(table_rows):
            for c, value in enumerate(row_values):
                table.rows[r].cells[c].text = value
    buf = io.BytesIO()
    doc.save(buf)
    return base64.b64encode(buf.getvalue()).decode()


def _text_pdf_base64(text: str) -> str:
    """Builds a minimal real-text single-page PDF using only pypdf's own
    object model (no reportlab dependency, since pypdf is already the
    hard dependency T-0.1's PDF path relies on)."""
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, StreamObject

    writer = PdfWriter()
    writer.add_blank_page(width=300, height=300)
    page = writer.pages[0]

    content = f"BT /F1 24 Tf 100 200 Td ({text}) Tj ET".encode()
    stream = StreamObject()
    stream.set_data(content)
    stream_ref = writer._add_object(stream)

    font = DictionaryObject()
    font[NameObject("/Type")] = NameObject("/Font")
    font[NameObject("/Subtype")] = NameObject("/Type1")
    font[NameObject("/BaseFont")] = NameObject("/Helvetica")
    font_ref = writer._add_object(font)

    font_dict = DictionaryObject()
    font_dict[NameObject("/F1")] = font_ref
    resources = DictionaryObject()
    resources[NameObject("/Font")] = font_dict

    page[NameObject("/Contents")] = stream_ref
    page[NameObject("/Resources")] = resources

    buf = io.BytesIO()
    writer.write(buf)
    return base64.b64encode(buf.getvalue()).decode()


def _blank_pdf_base64() -> str:
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    return base64.b64encode(buf.getvalue()).decode()


class TestIngestDocumentDocx(unittest.TestCase):
    def test_extracts_paragraphs_and_table_cells(self) -> None:
        b64 = _docx_base64(
            paragraphs=["John Smith", "Software Engineer with 10 years experience."],
            table_rows=[["Skill", "Python"]],
        )
        result = ingest_document(b64, "docx")
        self.assertTrue(result.passed)
        self.assertIn("John Smith", result.data["extracted_text"])
        self.assertIn("Python", result.data["extracted_text"])
        self.assertEqual(result.data["paragraph_count"], 4)

    def test_empty_docx_is_a_high_finding_not_a_silent_empty_string(self) -> None:
        b64 = _docx_base64(paragraphs=[])
        result = ingest_document(b64, "docx")
        self.assertFalse(result.passed)
        self.assertEqual(result.findings[0]["severity"], "High")
        self.assertEqual(result.data["extracted_text"], "")

    def test_whitespace_only_paragraphs_count_as_empty(self) -> None:
        b64 = _docx_base64(paragraphs=["   ", "\t"])
        result = ingest_document(b64, "docx")
        self.assertFalse(result.passed)


@unittest.skipUnless(_PYPDF_AVAILABLE, _SKIP_NO_PYPDF)
class TestIngestDocumentPdf(unittest.TestCase):
    def test_extracts_real_text(self) -> None:
        b64 = _text_pdf_base64("Jane Doe Senior Engineer")
        result = ingest_document(b64, "pdf")
        self.assertTrue(result.passed)
        self.assertIn("Jane Doe Senior Engineer", result.data["extracted_text"])
        self.assertEqual(result.data["page_count"], 1)

    def test_blank_pdf_with_no_text_layer_is_a_high_finding(self) -> None:
        b64 = _blank_pdf_base64()
        result = ingest_document(b64, "pdf")
        self.assertFalse(result.passed)
        self.assertEqual(result.findings[0]["severity"], "High")
        self.assertIn("scan", result.findings[0]["issue"].lower())


@unittest.skipIf(_PYPDF_AVAILABLE, "this test exercises the path taken specifically when pypdf is absent")
class TestIngestDocumentPdfWithoutPypdf(unittest.TestCase):
    def test_missing_pypdf_is_a_clean_critical_finding_not_a_crash(self) -> None:
        """Pins the actual design intent: pypdf is lazy-imported inside
        _ingest_pdf precisely so an environment without it still starts
        up fine and every docx-only path still works; a PDF ingest
        attempt should decline cleanly, not raise ImportError up
        through the tool call."""
        result = ingest_document(base64.b64encode(b"irrelevant").decode(), "pdf")
        self.assertFalse(result.passed)
        self.assertEqual(result.findings[0]["severity"], "Critical")
        self.assertIn("pypdf", result.findings[0]["issue"].lower())


class TestIngestDocumentInputHandling(unittest.TestCase):
    def test_invalid_base64_is_a_critical_finding_not_a_crash(self) -> None:
        result = ingest_document("not-valid-base64!!!", "docx")
        self.assertFalse(result.passed)
        self.assertEqual(result.findings[0]["severity"], "Critical")

    def test_unsupported_file_type_is_rejected(self) -> None:
        b64 = _docx_base64(paragraphs=["text"])
        result = ingest_document(b64, "txt")
        self.assertFalse(result.passed)
        self.assertIn("Unsupported file_type", result.findings[0]["issue"])


class TestValidateStructuredIntakeForm(unittest.TestCase):
    def test_all_required_fields_present_passes(self) -> None:
        result = validate_structured_intake_form(
            {"name": "Josh", "email": "j@example.com"}, ["name", "email"]
        )
        self.assertTrue(result.passed)

    def test_missing_field_is_critical(self) -> None:
        result = validate_structured_intake_form({"name": "Josh"}, ["name", "email", "target_role"])
        self.assertFalse(result.passed)
        self.assertEqual(result.data["missing_fields"], ["email", "target_role"])
        self.assertTrue(all(f["severity"] == "Critical" for f in result.findings))

    def test_blank_field_counts_as_missing(self) -> None:
        result = validate_structured_intake_form({"name": "  ", "email": "j@example.com"}, ["name", "email"])
        self.assertFalse(result.passed)
        self.assertEqual(result.data["missing_fields"], ["name"])

    def test_extra_unrequired_fields_are_ignored(self) -> None:
        result = validate_structured_intake_form(
            {"name": "Josh", "email": "j@x.com", "hobby": "chess"}, ["name", "email"]
        )
        self.assertTrue(result.passed)

    def test_empty_required_fields_list_always_passes(self) -> None:
        result = validate_structured_intake_form({}, [])
        self.assertTrue(result.passed)


if __name__ == "__main__":
    unittest.main()
