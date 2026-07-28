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


class TestUnresolvedMarkerGateIsReachable(unittest.TestCase):
    """T-6.14. A resume that ships containing "[ADD METRIC: ...]" is the
    single most embarrassing thing Iris could hand a job seeker, and
    require_no_unresolved_markers existed to stop it with ZERO callers
    anywhere in app/ until 2026-07-28. The tool of the same name was
    registered, so the model could choose to call it, which is precisely
    the model self-report spec rule 4.1 refuses to accept as
    enforcement.

    Unlike the two session-state gates beside it, this one is a pure
    function of the artifact being rendered, which is what makes it safe
    to enforce here: it cannot misfire on a correct document."""

    def setUp(self) -> None:
        self.session = Session(session_id="s", user_id="u")

    def test_an_unresolved_marker_blocks_a_deliverable(self) -> None:
        sections = [{"heading": "EXPERIENCE", "body": "Cut deployment time [ADD METRIC: by how much?]."}]
        result = _render(self.session, DELIVERABLE, sections)
        self.assertFalse(result.passed)
        self.assertEqual(result.data["blocked_by_gate"], "T-6.14")

    def test_blocking_produces_no_downloadable_file(self) -> None:
        """The enforcement is the absence of a file_id: no file stored,
        no file_ready event, no download button. The findings only make
        the reason legible."""
        sections = [{"heading": "EXPERIENCE", "body": "Grew revenue [ADD METRIC: percent]."}]
        result = _render(self.session, DELIVERABLE, sections)
        self.assertIsNone((result.data or {}).get("file_id"))

    def test_an_unresolved_marker_blocks_a_cover_letter_too(self) -> None:
        sections = [{"heading": "BODY", "body": "I led the migration [ADD METRIC: team size]."}]
        self.assertFalse(_render(self.session, COVER_LETTER, sections).passed)

    def test_a_clean_deliverable_still_renders(self) -> None:
        """The gate must not become a tax on correct documents."""
        sections = [{"heading": "EXPERIENCE", "body": "Cut deployment time by 40 percent."}]
        result = _render(self.session, DELIVERABLE, sections)
        self.assertTrue(result.passed, result.findings)
        self.assertIsNotNone(result.data["file_id"])

    def test_the_foundational_resume_is_exempt(self) -> None:
        """Deliberate, and consistent with the other delivery gates: the
        foundational resume is a source document, not something sent to
        an employer, and markers are legitimate work-in-progress there."""
        sections = [{"heading": "EXPERIENCE", "body": "Led the migration [ADD METRIC: team size]."}]
        self.assertTrue(_render(self.session, FOUNDATIONAL, sections).passed)


class TestSessionStateGatesAreDeliberatelyNotWiredHere(unittest.TestCase):
    """Guards a decision that looks like an omission.

    require_fit_check_completed (T-5.1) and require_registry_populated
    (T-5.2) are NOT enforced at render, and that is deliberate. Nothing
    in the codebase ever sets session.fit_check_completed to True:
    Phase 5 has zero registered tools, so there is nothing to set it.
    Adding that gate here would not restore a dormant protection, it
    would permanently block every tailored resume download.

    This test fails the moment someone "fixes" the omission, and points
    at the setter that has to exist first."""

    def test_a_tailored_render_succeeds_without_a_recorded_fit_check(self) -> None:
        session = Session(session_id="s", user_id="u")
        self.assertFalse(session.fit_check_completed)
        self.assertTrue(_render(session, DELIVERABLE).passed)

    def test_a_tailored_render_succeeds_with_an_empty_registry(self) -> None:
        session = Session(session_id="s", user_id="u")
        self.assertTrue(session.is_registry_empty())
        self.assertTrue(_render(session, DELIVERABLE).passed)

    def test_nothing_sets_fit_check_completed_to_true(self) -> None:
        """The precondition for wiring T-5.1. When this fails, a setter
        exists and the gate can be reconsidered."""
        import pathlib

        hits = []
        for path in pathlib.Path("app").rglob("*.py"):
            for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if "fit_check_completed" in line and "= True" in line:
                    hits.append(f"{path}:{i}")
        self.assertEqual(hits, [], f"A setter now exists ({hits}); reconsider wiring T-5.1.")


if __name__ == "__main__":
    unittest.main()
