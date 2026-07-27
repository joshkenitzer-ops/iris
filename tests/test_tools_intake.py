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


class TestRunBatchChecksAcceptsHybrid(unittest.TestCase):
    """Regression coverage for closing the spec/code gap: the spec says
    Phase 1's 15 checks "collapse to one turn" including the HYBRID
    nominators, but run_batch_checks used to reject anything that
    wasn't TOOL/GATE, forcing 8 of Phase 1's 15 checks into individual
    round trips (one of them, nominate_tense_inconsistency_candidates,
    multiplied by role count). Every HYBRID nominator's findings already
    embed the flagged text inline, so there's no data field a batched
    call would be discarding that the model actually needs."""

    def test_hybrid_check_runs_in_the_batch_instead_of_being_rejected(self) -> None:
        session, attachment_id = _session_with_docx_attachment(
            ["Led the migration and the rollout and the cleanup and the postmortem."]
        )
        ingest_document(attachment_id, session=session)
        # T-3.13 check_run_on_sentences is HYBRID — previously this would
        # have come back as "T-3.13 is HYBRID — call it separately."
        result = run_batch_checks(
            tool_ids=["T-3.13"], inputs={"attachment_id": attachment_id}, session=session
        )
        self.assertFalse(result.passed)
        self.assertTrue(any("run-on" in f["issue"].lower() for f in result.findings))
        self.assertEqual(result.data["summary"], [{"tool_id": "T-3.13", "passed": False}])

    def test_hybrid_and_tool_checks_batch_together_in_one_call(self) -> None:
        session, attachment_id = _session_with_docx_attachment(
            ["Used seamlessly integrated systems and participated in the rollout."]
        )
        ingest_document(attachment_id, session=session)
        # T-3.3 (TOOL) and T-3.11 (HYBRID) in the same call — this is
        # exactly the mixed Phase 1 batch the model is now told to send.
        result = run_batch_checks(
            tool_ids=["T-3.3", "T-3.11"], inputs={"attachment_id": attachment_id}, session=session
        )
        self.assertFalse(result.passed)
        self.assertTrue(any("seamlessly" in f["issue"] for f in result.findings))
        self.assertTrue(any("hedge" in f["issue"].lower() for f in result.findings))

    def test_hybrid_check_with_extra_required_arg_reads_it_from_shared_inputs(self) -> None:
        session, attachment_id = _session_with_docx_attachment(
            ["Worked extensively with Kubernetes to ship the platform."]
        )
        ingest_document(attachment_id, session=session)
        # T-3.16 needs known_terms in addition to text/attachment_id.
        result = run_batch_checks(
            tool_ids=["T-3.16"],
            inputs={"attachment_id": attachment_id, "known_terms": ["Kubernetes"]},
            session=session,
        )
        self.assertFalse(result.passed)
        self.assertTrue(any("Kubernetes" in f["issue"] for f in result.findings))

    def test_judgment_and_human_kinds_are_still_rejected(self) -> None:
        # Confirms the loosened gate didn't turn into "accept everything" —
        # only TOOL/GATE/HYBRID dispatch here; nothing in the registry is
        # actually JUDGMENT/HUMAN kind right now, so this locks in intent
        # via the source check_run_on_sentences already exercises: kinds
        # outside (TOOL, GATE, HYBRID) still produce the "call it
        # separately" finding rather than being silently dispatched.
        from app.enforcement import EnforcementKind, registry

        non_batchable = [
            spec.id for spec in registry._by_id.values()
            if spec.kind not in (EnforcementKind.TOOL, EnforcementKind.GATE, EnforcementKind.HYBRID)
        ]
        if not non_batchable:
            self.skipTest("No JUDGMENT/HUMAN-kind tool registered to exercise this against.")
        session, attachment_id = _session_with_docx_attachment(["Jane Doe"])
        ingest_document(attachment_id, session=session)
        result = run_batch_checks(
            tool_ids=[non_batchable[0]], inputs={"attachment_id": attachment_id}, session=session
        )
        self.assertFalse(result.passed)
        self.assertIn("call it separately", result.findings[0]["issue"])


class TestRunBatchChecksAcrossLaterPhases(unittest.TestCase):
    """Regression coverage for extending run_batch_checks' documented
    batch lists past Phase 1: Phases 0, 2, 5, and 7 previously had no
    batching guidance at all, and Phases 4/8 only listed part of their
    spec-documented check set. Unlike Phase 1's uniform `text`/
    `attachment_id` shape, most of these tools take different,
    tool-specific keys (lead_text, bullets, headline_text, ...) in the
    same shared inputs dict — this verifies dispatch_by_id's per-tool
    signature filtering actually routes each key to the right tool
    when several very differently-shaped tools share one batch call."""

    def test_phase_0_batches_numeric_and_list_shaped_inputs_together(self) -> None:
        session = Session(session_id="s", user_id="u")
        result = run_batch_checks(
            tool_ids=["T-0.2", "T-0.8"],
            inputs={
                # T-0.2 — numeric signals the model computed itself.
                "ocr_confidence": 0.5,
                "replacement_char_ratio": 0.0,
                "role_blocks_with_dates": 4,
                "date_parse_failure_ratio": 0.0,
                # T-0.8 — a list of candidate bullet strings.
                "items": ["Led migration of billing service to AWS.", "Led migration of the billing service to AWS."],
            },
            session=session,
        )
        self.assertFalse(result.passed)  # low ocr_confidence trips T-0.2; near-dupes trip T-0.8
        self.assertEqual(
            {row["tool_id"]: row["passed"] for row in result.data["summary"]},
            {"T-0.2": False, "T-0.8": False},
        )

    def test_phase_2_batches_six_different_per_section_keys(self) -> None:
        session = Session(session_id="s", user_id="u")
        result = run_batch_checks(
            tool_ids=["T-2.2", "T-2.4", "T-2.8", "T-6.6"],
            inputs={
                "lead_text": "Shipped the redesign",  # 3 words — passes T-2.2's 3-6 range
                "summary_text": "Led the platform rebuild end to end.",
                "section_order": ["NAME", "HEADLINE", "CONTACT", "SUMMARY", "SKILLS", "EXPERIENCE"],
                "bullets": ["Did a thing.", "Did another thing.", "Did a third thing."],
            },
            session=session,
        )
        summary = {row["tool_id"]: row["passed"] for row in result.data["summary"]}
        # Not asserting every check passes (that's each tool's own unit
        # test's job) — asserting all four actually ran, meaning each
        # pulled its own key out of one shared dict instead of colliding
        # or getting skipped.
        self.assertEqual(set(summary.keys()), {"T-2.2", "T-2.4", "T-2.8", "T-6.6"})
        self.assertTrue(summary["T-2.2"])  # 3-word lead is in range

    def test_phase_4_batches_docx_based_and_snippet_based_checks_together(self) -> None:
        session, attachment_id = _session_with_docx_attachment(["Jane Doe", "Senior Engineer"])
        ingest_document(attachment_id, session=session)
        result = run_batch_checks(
            tool_ids=["T-4.1", "T-4.5"],
            inputs={
                "attachment_id": attachment_id,  # resolves docx_base64 for T-4.1
                "date_range_text": "Jan 2020 - Mar 2022",  # T-4.5 reads this directly
            },
            session=session,
        )
        summary = {row["tool_id"]: row["passed"] for row in result.data["summary"]}
        self.assertEqual(set(summary.keys()), {"T-4.1", "T-4.5"})
        self.assertTrue(summary["T-4.1"])  # plain paragraphs, no tables
        self.assertTrue(summary["T-4.5"])  # well-formed date range

    def test_phase_5_batches_headline_and_jd_coverage_checks(self) -> None:
        session = Session(session_id="s", user_id="u")
        result = run_batch_checks(
            tool_ids=["T-6.7", "T-6.8"],
            inputs={
                "headline_text": "Senior Software Engineer",
                "posting_title": "Senior Software Engineer",
                "jd_phrases": ["kubernetes", "distributed systems"],
                "resume_text": "Built distributed systems on Kubernetes at scale.",
            },
            session=session,
        )
        summary = {row["tool_id"]: row["passed"] for row in result.data["summary"]}
        self.assertEqual(set(summary.keys()), {"T-6.7", "T-6.8"})
        self.assertTrue(summary["T-6.7"])  # exact title match

    def test_phase_7_batches_letter_text_and_salutation_checks(self) -> None:
        session = Session(session_id="s", user_id="u")
        letter = "\n\n".join(["Paragraph one.", "Paragraph two.", "Paragraph three."])
        result = run_batch_checks(
            tool_ids=["T-7.1", "T-7.4"],
            inputs={"letter_text": letter, "salutation": "Dear Hiring Manager,"},
            session=session,
        )
        summary = {row["tool_id"]: row["passed"] for row in result.data["summary"]}
        self.assertEqual(set(summary.keys()), {"T-7.1", "T-7.4"})

    def test_phase_8_batches_the_previously_missing_docx_checks(self) -> None:
        session, attachment_id = _session_with_docx_attachment(["Jane Doe", "Senior Engineer"])
        ingest_document(attachment_id, session=session)
        # T-8.13 (check_illegal_characters) was missing from the
        # documented Phase 8 list even though it's docx-based just like
        # the checks already there.
        result = run_batch_checks(
            tool_ids=["T-8.5", "T-8.13"], inputs={"attachment_id": attachment_id}, session=session
        )
        summary = {row["tool_id"]: row["passed"] for row in result.data["summary"]}
        self.assertEqual(set(summary.keys()), {"T-8.5", "T-8.13"})


if __name__ == "__main__":
    unittest.main()
