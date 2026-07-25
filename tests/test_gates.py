import unittest

from app.gates import (
    GateBlocked,
    check_profile_fingerprint,
    require_no_open_criticals,
    require_no_unresolved_markers,
    require_phase1_disposition,
    require_registry_populated,
)
from app.session import Fact, Finding, Session


class TestRequireRegistryPopulated(unittest.TestCase):
    def test_empty_registry_blocks(self) -> None:
        session = Session(session_id="s", user_id="u")
        with self.assertRaises(GateBlocked) as ctx:
            require_registry_populated(session)
        self.assertEqual(ctx.exception.gate_id, "T-5.2")

    def test_populated_registry_passes(self) -> None:
        session = Session(session_id="s", user_id="u")
        session.registry["F-001"] = Fact(id="F-001", type="skill", value="Python", statement="Uses Python.")
        require_registry_populated(session)  # should not raise

    def test_only_superseded_facts_counts_as_empty(self) -> None:
        session = Session(session_id="s", user_id="u")
        session.registry["F-001"] = Fact(
            id="F-001", type="skill", value="Python", statement="Uses Python.", status="superseded"
        )
        with self.assertRaises(GateBlocked):
            require_registry_populated(session)


class TestRequirePhase1Disposition(unittest.TestCase):
    def test_undispositioned_critical_blocks(self) -> None:
        session = Session(session_id="s", user_id="u")
        session.findings.append(
            Finding(id="f1", tool_id="T-1.5", severity="Critical", issue="x", fix="y", dispositioned=False)
        )
        with self.assertRaises(GateBlocked) as ctx:
            require_phase1_disposition(session)
        self.assertEqual(ctx.exception.gate_id, "T-1.8")

    def test_dispositioned_with_reason_passes(self) -> None:
        session = Session(session_id="s", user_id="u")
        session.findings.append(
            Finding(
                id="f1",
                tool_id="T-1.5",
                severity="Critical",
                issue="x",
                fix="y",
                dispositioned=True,
                disposition_reason="Acknowledged, low-relevance role, will not fix.",
            )
        )
        require_phase1_disposition(session)  # should not raise

    def test_non_phase1_critical_does_not_block_phase1_check(self) -> None:
        session = Session(session_id="s", user_id="u")
        session.findings.append(
            Finding(id="f1", tool_id="T-8.2", severity="Critical", issue="x", fix="y", dispositioned=False)
        )
        require_phase1_disposition(session)  # T-8.* is a different gate, should not raise here


class TestRequireNoOpenCriticals(unittest.TestCase):
    def test_open_critical_blocks_delivery(self) -> None:
        session = Session(session_id="s", user_id="u")
        session.findings.append(
            Finding(id="f1", tool_id="T-8.2", severity="Critical", issue="x", fix="y")
        )
        with self.assertRaises(GateBlocked) as ctx:
            require_no_open_criticals(session)
        self.assertEqual(ctx.exception.gate_id, "T-8.18")

    def test_dismissed_critical_does_not_block(self) -> None:
        """Critical findings should not be dismissible per spec, but
        this gate is a pure state check; it trusts session.findings as
        given. The rule that a Critical is never marked dismissed
        belongs to whatever code sets dismissed=True, not here. This
        test documents that boundary rather than re-enforcing it."""
        session = Session(session_id="s", user_id="u")
        session.findings.append(
            Finding(id="f1", tool_id="T-8.2", severity="Critical", issue="x", fix="y", dismissed=True)
        )
        require_no_open_criticals(session)  # should not raise, given dismissed=True

    def test_high_severity_does_not_block(self) -> None:
        session = Session(session_id="s", user_id="u")
        session.findings.append(
            Finding(id="f1", tool_id="T-8.2", severity="High", issue="x", fix="y")
        )
        require_no_open_criticals(session)  # should not raise


class TestUnresolvedMarkers(unittest.TestCase):
    def test_clean_text_passes(self) -> None:
        require_no_unresolved_markers("Reduced onboarding time by two weeks.")  # no raise

    def test_marker_blocks(self) -> None:
        with self.assertRaises(GateBlocked) as ctx:
            require_no_unresolved_markers("Reduced onboarding time by [ADD METRIC: percent] percent.")
        self.assertEqual(ctx.exception.gate_id, "T-6.14")


class TestProfileFingerprint(unittest.TestCase):
    def test_first_upload_sets_fingerprint_and_matches(self) -> None:
        session = Session(session_id="s", user_id="u")
        self.assertTrue(check_profile_fingerprint(session, "abc123"))
        self.assertEqual(session.master_fingerprint, "abc123")

    def test_mismatch_returns_false_but_never_raises(self) -> None:
        session = Session(session_id="s", user_id="u", master_fingerprint="abc123")
        result = check_profile_fingerprint(session, "different-hash")
        self.assertFalse(result)  # T-2.19: warn, never block


if __name__ == "__main__":
    unittest.main()
