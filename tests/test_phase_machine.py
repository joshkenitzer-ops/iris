"""The phase machine, made real (2026-07-28).

Before this, Phase existed, /advance-phase was fully implemented and
correct, and nothing called it. Every session sat in STARTING_POINT for
its entire life, so every gate hanging off a phase boundary was inert:
T-1.8 never blocked a Foundational Build over an unresolved audit
Critical, and T-5.2 never blocked a Fit Check on an empty registry.
Both were shipped protections that had never once protected anyone.

Two things had to be true at once for this to be safe:

  - advancement has to be something the MODEL invokes, because knowing
    a phase's work is finished is judgment, not computation; and
  - permission has to be decided by CODE, because a phase entered on
    the strength of an assertion is not gated at all.

Everything here goes through registry.dispatch, the path a real model
tool call takes. A test that calls advance_phase_tool directly would
prove the function works, which is exactly what the old /advance-phase
tests proved while nothing called the route.
"""

import unittest

import app.tools  # noqa: F401  (registers the tools)
from app.enforcement import registry
from app.session import Fact, Finding, Phase, Session


def _advance(session: Session, target: str):
    return registry.dispatch("advance_phase", {"target_phase": target}, session=session)


def _phase1_critical(dispositioned: bool = False) -> Finding:
    return Finding(
        id="F-T-1.1",
        tool_id="T-1.1",
        severity="Critical",
        issue="Unverifiable figure in the summary.",
        fix="Cite the source or remove it.",
        dispositioned=dispositioned,
        disposition_reason="Acknowledged, figure is from a sealed review." if dispositioned else None,
    )


def _fact(fact_id: str = "F1") -> Fact:
    return Fact(
        id=fact_id,
        type="metric",
        value="40 percent",
        statement="Cut deployment time by 40 percent.",
    )


class TestAdvancementIsReachable(unittest.TestCase):
    """The property whose absence made every phase gate decorative."""

    def setUp(self) -> None:
        self.session = Session(session_id="s", user_id="u")

    def test_a_session_starts_at_the_starting_point(self) -> None:
        self.assertEqual(self.session.phase, Phase.STARTING_POINT)

    def test_advancing_through_dispatch_moves_the_session(self) -> None:
        result = _advance(self.session, "AUDIT")
        self.assertTrue(result.passed, result.findings)
        self.assertEqual(self.session.phase, Phase.AUDIT)
        self.assertEqual(result.data["phase"], "AUDIT")
        self.assertEqual(result.data["previous_phase"], "STARTING_POINT")

    def test_the_tool_is_registered_as_a_gate(self) -> None:
        """Not a TOOL. It refuses transitions, which is what GATE
        means, and test_spec_sync checks the tool list agrees."""
        spec = registry.get_by_name("advance_phase")
        self.assertEqual(spec.kind.value, "GATE")
        self.assertTrue(spec.needs_session)

    def test_phase_is_never_taken_from_model_input(self) -> None:
        """The session is injected by the harness, never supplied by
        the model (spec 7.6 / T-9.12). A target phase is a request; it
        can never carry an identity or a session to act on."""
        spec = registry.get_by_name("advance_phase")
        self.assertEqual(set(spec.input_schema["properties"]), {"target_phase"})


class TestGatesNowActuallyBlock(unittest.TestCase):
    def setUp(self) -> None:
        self.session = Session(session_id="s", user_id="u")

    def test_an_undispositioned_audit_critical_blocks_the_build(self) -> None:
        """T-1.8, firing in production for the first time."""
        self.session.findings.append(_phase1_critical())
        result = _advance(self.session, "FOUNDATIONAL_BUILD")
        self.assertFalse(result.passed)
        self.assertEqual(result.data["blocked_by_gate"], "T-1.8")

    def test_a_dispositioned_critical_does_not_block(self) -> None:
        """Fixed or acknowledged-with-reason both satisfy T-1.8. The
        gate demands a decision, not a particular decision."""
        self.session.findings.append(_phase1_critical(dispositioned=True))
        self.assertTrue(_advance(self.session, "FOUNDATIONAL_BUILD").passed)

    def test_an_empty_registry_blocks_the_fit_check(self) -> None:
        """T-5.2 / spec 5.9."""
        self.assertTrue(self.session.is_registry_empty())
        result = _advance(self.session, "FIT_CHECK")
        self.assertFalse(result.passed)
        self.assertEqual(result.data["blocked_by_gate"], "T-5.2")

    def test_a_populated_registry_permits_the_fit_check(self) -> None:
        self.session.registry["F1"] = _fact()
        self.assertTrue(_advance(self.session, "FIT_CHECK").passed)

    def test_tailoring_is_blocked_until_the_fit_check_has_run(self) -> None:
        """T-5.1. Unenforceable before 2026-07-28 because nothing set
        the flag it reads."""
        self.session.registry["F1"] = _fact()
        result = _advance(self.session, "TAILORING")
        self.assertFalse(result.passed)
        self.assertEqual(result.data["blocked_by_gate"], "T-5.1")


class TestARefusedAdvanceIsRecoverable(unittest.TestCase):
    """A gate that strands a user is worse than the risk it covers.
    Every refusal has to leave the session usable and say what to do."""

    def setUp(self) -> None:
        self.session = Session(session_id="s", user_id="u")
        self.session.findings.append(_phase1_critical())

    def test_the_session_stays_where_it_was(self) -> None:
        _advance(self.session, "FOUNDATIONAL_BUILD")
        self.assertEqual(self.session.phase, Phase.STARTING_POINT)

    def test_the_refusal_names_the_gate_and_the_current_phase(self) -> None:
        result = _advance(self.session, "FOUNDATIONAL_BUILD")
        self.assertEqual(result.data["phase"], "STARTING_POINT")
        self.assertIn("T-1.8", result.findings[0]["issue"])
        self.assertIn("STARTING_POINT", result.findings[0]["fix"])

    def test_doing_the_missing_work_unblocks_it(self) -> None:
        """The whole point: refusal is a redirect, never a dead end."""
        self.assertFalse(_advance(self.session, "FOUNDATIONAL_BUILD").passed)
        self.session.findings[0].dispositioned = True
        self.session.findings[0].disposition_reason = "Figure verified against the sealed review."
        self.assertTrue(_advance(self.session, "FOUNDATIONAL_BUILD").passed)
        self.assertEqual(self.session.phase, Phase.FOUNDATIONAL_BUILD)

    def test_an_unknown_phase_name_is_refused_without_raising(self) -> None:
        result = _advance(self.session, "NOT_A_PHASE")
        self.assertFalse(result.passed)
        self.assertEqual(self.session.phase, Phase.STARTING_POINT)
        self.assertIn("FOUNDATIONAL_BUILD", result.findings[0]["fix"])

    def test_phase_names_are_accepted_case_insensitively(self) -> None:
        session = Session(session_id="s2", user_id="u")
        self.assertTrue(_advance(session, "audit").passed)
        self.assertEqual(session.phase, Phase.AUDIT)


class TestFitCheckCompletionIsDerived(unittest.TestCase):
    """T-5.1's precondition, and the reason wiring it is now safe.

    A record_fit_check_complete tool would have been the obvious fix
    and the wrong one: it is exactly the model self-report spec rule
    4.1 refuses to accept as enforcement. The flag is instead a side
    effect of the deterministic comparison actually running."""

    def setUp(self) -> None:
        self.session = Session(session_id="s", user_id="u")
        self.session.registry["F1"] = _fact()

    def _run_fit_check(self):
        return registry.dispatch(
            "check_jd_phrase_coverage",
            {"jd_phrases": ["roadmap"], "resume_text": "Owned the product roadmap."},
            session=self.session,
        )

    def test_the_flag_starts_false(self) -> None:
        self.assertFalse(self.session.fit_check_completed)

    def test_running_the_fit_check_sets_it(self) -> None:
        self._run_fit_check()
        self.assertTrue(self.session.fit_check_completed)

    def test_it_is_set_even_when_coverage_fails(self) -> None:
        """Missing JD phrases mean the resume needs work, not that the
        Fit Check did not happen. Tying the flag to passed would make a
        thorough check that found real gaps count for less than a
        superficial one that found none."""
        registry.dispatch(
            "check_jd_phrase_coverage",
            {"jd_phrases": ["kubernetes"], "resume_text": "Owned the product roadmap."},
            session=self.session,
        )
        self.assertTrue(self.session.fit_check_completed)

    def test_the_fit_check_unblocks_tailoring_end_to_end(self) -> None:
        self.assertFalse(_advance(self.session, "TAILORING").passed)
        self._run_fit_check()
        self.assertTrue(_advance(self.session, "TAILORING").passed)

    def test_a_new_job_description_invalidates_the_prior_run(self) -> None:
        """T-5.1 requires a Fit Check on EVERY submission. A pass
        against a previous JD must not satisfy the next one."""
        self._run_fit_check()
        self.assertTrue(self.session.fit_check_completed)
        registry.dispatch(
            "ingest_job_description",
            {"jd_text": "A completely different role at a different company."},
            session=self.session,
        )
        self.assertFalse(self.session.fit_check_completed)
        self.assertFalse(_advance(self.session, "TAILORING").passed)


if __name__ == "__main__":
    unittest.main()
