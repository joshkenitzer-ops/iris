"""
Regression coverage for the unreachable-delivery-gate fix (2026-07-27).

The gates were never wrong. They were never called. T-8.18 and T-7.8 ran
only inside POST /sessions/{id}/deliver, which nothing in the product
invokes (static/app.js has no reference to it), so every session sat in
STARTING_POINT and both gates were dead in production while passing
their own tests, because those tests POST the route directly.

These tests therefore assert REACHABILITY, not gate correctness: they go
through registry.dispatch, the same path a model tool call takes, rather
than calling the gate functions. A test that calls the gate directly is
exactly the kind that passed while the product shipped ungated.
"""

import unittest

import app.tools  # noqa: F401  (import for its decorator side effects: registers the tools)
from app.enforcement import registry
from app.session import Finding, Session

DELIVERABLE = "Kenitzer_Joshua_Resume_Acme_SrIDDev_V1.docx"
COVER_LETTER = "Kenitzer_Joshua_CoverLetter_Acme_SrIDDev_V1.docx"
FOUNDATIONAL = "Kenitzer_Joshua_Resume_Foundational_2026-07-27.docx"

SECTIONS = [{"heading": "EXPERIENCE", "body": "Led the platform migration."}]


def _render(session: Session, filename: str, sections=None):
    """Dispatches by tool name, the way a real model tool call arrives."""
    return registry.dispatch(
        "render_resume_docx",
        {"sections": sections or SECTIONS, "filename": filename},
        session=session,
    )


def _critical(tool_id: str = "T-8.2", dispositioned: bool = False) -> Finding:
    return Finding(
        id=f"F-{tool_id}",
        tool_id=tool_id,
        severity="Critical",
        issue="Claim not supported by the registry.",
        fix="Remove or source it.",
        dispositioned=dispositioned,
    )


class TestDeliverableRenderIsGated(unittest.TestCase):
    def setUp(self) -> None:
        self.session = Session(session_id="s", user_id="u")

    def test_open_critical_blocks_a_tailored_resume(self) -> None:
        self.session.findings.append(_critical())
        result = _render(self.session, DELIVERABLE)
        self.assertFalse(result.passed)
        self.assertEqual(result.data["blocked_by_gate"], "T-8.18")

    def test_open_critical_blocks_a_cover_letter(self) -> None:
        self.session.findings.append(_critical())
        result = _render(self.session, COVER_LETTER)
        self.assertFalse(result.passed)

    def test_blocked_render_stores_no_file_at_all(self) -> None:
        """The actual teeth. No stored file means no file_id, which means
        the harness emits no file_ready event, which means no download
        button. A finding the model could talk past is not enforcement;
        the absence of a downloadable artifact is."""
        self.session.findings.append(_critical())
        _render(self.session, DELIVERABLE)
        self.assertEqual(len(self.session.rendered_files), 0)

    def test_clean_session_still_renders_a_deliverable(self) -> None:
        result = _render(self.session, DELIVERABLE)
        self.assertTrue(result.passed)
        self.assertIn("file_id", result.data)
        self.assertEqual(len(self.session.rendered_files), 1)

    def test_dismissed_critical_does_not_block(self) -> None:
        finding = _critical()
        finding.severity = "High"  # only Criticals gate; High is advisory
        self.session.findings.append(finding)
        self.assertTrue(_render(self.session, DELIVERABLE).passed)


class TestFoundationalRenderIsNotGated(unittest.TestCase):
    """Spec Phase 2: the foundational resume is "the source document,
    not a document to send," and Iris renders it immediately on
    Foundational Build completion, long before Final Review. Gating it
    would break Phase 2."""

    def setUp(self) -> None:
        self.session = Session(session_id="s", user_id="u")

    def test_foundational_renders_with_an_open_critical(self) -> None:
        self.session.findings.append(_critical())
        result = _render(self.session, FOUNDATIONAL)
        self.assertTrue(result.passed)
        self.assertIn("file_id", result.data)

    def test_acknowledged_phase1_critical_still_lets_the_foundational_render(self) -> None:
        """The specific case a naive fix breaks. A Phase 1 Critical the
        user acknowledged with a stated reason satisfies
        require_phase1_disposition, but open_criticals() still counts it,
        since dispositioned is not dismissed. Gating every render would
        have locked these users out of Foundational Build entirely."""
        self.session.findings.append(_critical(tool_id="T-1.3", dispositioned=True))
        self.assertEqual(len(self.session.undispositioned_phase1_criticals()), 0)
        self.assertEqual(len(self.session.open_criticals()), 1)
        self.assertTrue(_render(self.session, FOUNDATIONAL).passed)

    def test_foundational_with_a_version_suffix_is_still_foundational(self) -> None:
        self.session.findings.append(_critical())
        self.assertTrue(_render(self.session, "Kenitzer_Joshua_Resume_Foundational_2026-07-27_v2.docx").passed)


class TestUnrecognizedFilenameFailsClosed(unittest.TestCase):
    def test_unknown_filename_shape_is_treated_as_a_deliverable(self) -> None:
        """An unrecognized name must not be a way around the gate.
        check_filename_pattern (T-4.13) should have rejected it earlier;
        this is the backstop."""
        session = Session(session_id="s", user_id="u")
        session.findings.append(_critical())
        result = _render(session, "whatever.docx")
        self.assertFalse(result.passed)


class TestGapRemovalGateOnRender(unittest.TestCase):
    """T-7.8, unreachable for the same reason as T-8.18."""

    def setUp(self) -> None:
        self.session = Session(session_id="s", user_id="u")
        self.session.fit_check_gaps = ["Section 508 accessibility"]

    def test_silently_dropped_gap_blocks_delivery(self) -> None:
        result = _render(self.session, COVER_LETTER)
        self.assertFalse(result.passed)
        self.assertEqual(result.data["blocked_by_gate"], "T-7.8")

    def test_gap_present_in_the_rendered_text_passes(self) -> None:
        sections = [{"heading": "BODY", "body": "I have no Section 508 accessibility experience yet."}]
        self.assertTrue(_render(self.session, COVER_LETTER, sections).passed)

    def test_acknowledged_gap_removal_passes(self) -> None:
        self.session.gap_acknowledgments["Section 508 accessibility"] = "Covered verbally in the cover letter close."
        self.assertTrue(_render(self.session, COVER_LETTER).passed)

    def test_foundational_render_is_unaffected_by_an_unmet_gap(self) -> None:
        self.assertTrue(_render(self.session, FOUNDATIONAL).passed)


if __name__ == "__main__":
    unittest.main()
