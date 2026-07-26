import base64
import io
import unittest

from docx import Document

from app.session import Session
from app.tools.intake import (
    check_career_inventory_schema,
    find_near_duplicate_candidates,
    ingest_document,
    route_low_confidence_to_manual_review,
    run_batch_checks,
    score_extraction_confidence,
)


class TestScoreExtractionConfidence(unittest.TestCase):
    def test_clean_extraction_passes(self) -> None:
        result = score_extraction_confidence(
            ocr_confidence=0.98,
            replacement_char_ratio=0.0,
            role_blocks_with_dates=4,
            date_parse_failure_ratio=0.0,
        )
        self.assertTrue(result.passed)
        self.assertEqual(result.data["tripped_signals"], [])

    def test_low_ocr_confidence_trips(self) -> None:
        result = score_extraction_confidence(
            ocr_confidence=0.5,
            replacement_char_ratio=0.0,
            role_blocks_with_dates=4,
            date_parse_failure_ratio=0.0,
        )
        self.assertFalse(result.passed)
        self.assertTrue(any("ocr_confidence" in s for s in result.data["tripped_signals"]))

    def test_too_few_role_blocks_trips(self) -> None:
        result = score_extraction_confidence(
            ocr_confidence=0.98,
            replacement_char_ratio=0.0,
            role_blocks_with_dates=1,
            date_parse_failure_ratio=0.0,
        )
        self.assertFalse(result.passed)

    def test_multiple_signals_all_reported(self) -> None:
        result = score_extraction_confidence(
            ocr_confidence=0.1,
            replacement_char_ratio=0.5,
            role_blocks_with_dates=0,
            date_parse_failure_ratio=0.9,
        )
        self.assertFalse(result.passed)
        self.assertEqual(len(result.data["tripped_signals"]), 4)


class TestRouteLowConfidence(unittest.TestCase):
    def test_passed_extraction_does_not_route(self) -> None:
        result = route_low_confidence_to_manual_review(extraction_passed=True)
        self.assertTrue(result.passed)

    def test_failed_extraction_routes(self) -> None:
        result = route_low_confidence_to_manual_review(
            extraction_passed=False, tripped_signals=["ocr_confidence low"]
        )
        self.assertFalse(result.passed)
        self.assertEqual(result.data["tripped_signals"], ["ocr_confidence low"])


class TestCareerInventorySchema(unittest.TestCase):
    def test_all_required_present_passes(self) -> None:
        result = check_career_inventory_schema(
            {"NAME": "Jane Doe", "CONTACT": "j@x.com|555|Buffalo, NY|", "SKILLS": "Python", "EXPERIENCE": "..."}
        )
        self.assertTrue(result.passed)

    def test_missing_required_section_is_critical(self) -> None:
        result = check_career_inventory_schema({"NAME": "Jane Doe"})
        self.assertFalse(result.passed)
        critical = [f for f in result.findings if f["severity"] == "Critical"]
        self.assertEqual(len(critical), 3)  # CONTACT, SKILLS, EXPERIENCE missing

    def test_unknown_section_flagged(self) -> None:
        result = check_career_inventory_schema(
            {
                "NAME": "Jane Doe",
                "CONTACT": "j@x.com|555|Buffalo, NY|",
                "SKILLS": "Python",
                "EXPERIENCE": "...",
                "HOBBIES": "Chess",
            }
        )
        self.assertFalse(result.passed)
        self.assertIn("HOBBIES", result.data["unknown_sections"])

    def test_generated_section_supplied_directly_is_low_severity_note(self) -> None:
        result = check_career_inventory_schema(
            {
                "NAME": "Jane Doe",
                "CONTACT": "j@x.com|555|Buffalo, NY|",
                "SKILLS": "Python",
                "EXPERIENCE": "...",
                "HEADLINE": "Senior PM",
            }
        )
        self.assertFalse(result.passed)  # not Critical, but not silently passed either
        self.assertTrue(any(f["severity"] == "Low" for f in result.findings))


class TestNearDuplicateCandidates(unittest.TestCase):
    def test_distinct_items_pass(self) -> None:
        result = find_near_duplicate_candidates(["Led migration to AWS.", "Managed a team of five."])
        self.assertTrue(result.passed)

    def test_near_identical_items_nominated(self) -> None:
        result = find_near_duplicate_candidates(
            ["Led migration of billing service to AWS.", "Led migration of the billing service to AWS."]
        )
        self.assertFalse(result.passed)
        self.assertEqual(len(result.data["candidates"]), 1)

    def test_threshold_is_respected(self) -> None:
        result = find_near_duplicate_candidates(
            ["Led migration to AWS.", "Managed onboarding redesign."], threshold=0.99
        )
        self.assertTrue(result.passed)


def _session_with_docx_attachment(paragraphs) -> tuple:
    doc = Document()
    for text in paragraphs:
        doc.add_paragraph(text)
    buf = io.BytesIO()
    doc.save(buf)
    session = Session(session_id="s", user_id="u")
    attachment = session.add_attachment(
        filename="resume.docx", file_type="docx", file_base64=base64.b64encode(buf.getvalue()).decode()
    )
    return session, attachment.id


class TestRunBatchChecksTextResolution(unittest.TestCase):
    """Regression coverage for the latency fix: run_batch_checks must
    resolve `text` for Phase 1 checks from the attachment's cached
    extracted_text server-side, the same way it already resolves
    `docx_base64` from attachment_id. The model must never be asked to
    paste extracted_text back into a tool call — doing so means
    generating tens of thousands of characters of output tokens, which
    is what caused score_extraction_confidence and later turns to slow
    down ~100x once the extraction-stripping bug (T-0.1 data loss) was
    fixed and extracted_text started actually reaching the model."""

    def test_attachment_id_resolves_to_cached_text_for_a_text_check(self) -> None:
        session, attachment_id = _session_with_docx_attachment(
            ["Jane Doe", "Used seamlessly integrated systems."]
        )
        ingest_result = ingest_document(attachment_id, session=session)
        self.assertTrue(ingest_result.passed)

        # T-3.3 check_banned_vocabulary takes `text`; the model here only
        # ever hands over attachment_id, never the extracted text itself.
        result = run_batch_checks(
            tool_ids=["T-3.3"], inputs={"attachment_id": attachment_id}, session=session
        )
        self.assertFalse(result.passed)  # "seamlessly" is an always-flagged term
        self.assertTrue(any("seamlessly" in f["issue"] for f in result.findings))

    def test_missing_cached_text_reports_a_finding_not_a_crash(self) -> None:
        # No ingest_document call, so attachment.extracted_text is still None.
        session, attachment_id = _session_with_docx_attachment(["Jane Doe"])
        result = run_batch_checks(
            tool_ids=["T-3.1"], inputs={"attachment_id": attachment_id}, session=session
        )
        self.assertFalse(result.passed)
        per_tool = result.data["summary"]
        self.assertEqual(per_tool, [{"tool_id": "T-3.1", "passed": False}])

    def test_explicit_text_input_still_takes_priority_over_cache(self) -> None:
        session, attachment_id = _session_with_docx_attachment(["Jane Doe"])
        ingest_document(attachment_id, session=session)
        result = run_batch_checks(
            tool_ids=["T-3.1"],
            inputs={"attachment_id": attachment_id, "text": "an em dash — right here"},
            session=session,
        )
        self.assertFalse(result.passed)  # would pass if the cached (dash-free) text won instead

    def test_docx_based_checks_still_resolve_docx_base64_unchanged(self) -> None:
        session, attachment_id = _session_with_docx_attachment(["Jane Doe", "Senior Engineer"])
        ingest_document(attachment_id, session=session)
        # T-3.2 (check_em_dash_in_docx) reads docx_base64, not text — this
        # is the pre-existing resolution path and must keep working.
        result = run_batch_checks(
            tool_ids=["T-3.2"], inputs={"attachment_id": attachment_id}, session=session
        )
        self.assertTrue(result.passed)


if __name__ == "__main__":
    unittest.main()
