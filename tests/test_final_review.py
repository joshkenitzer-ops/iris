import unittest

from app.session import Fact, Session
from app.tools.final_review import (
    check_full_slop_scan,
    check_locked_fact_scope,
    enumerate_unused_foundational_bullets,
    record_fix_attempt,
)


class TestFullSlopScan(unittest.TestCase):
    def test_clean_text_passes(self) -> None:
        result = check_full_slop_scan("Reduced onboarding time from 2 months to 2 weeks.")
        self.assertTrue(result.passed)

    def test_em_dash_surfaces_in_composite(self) -> None:
        result = check_full_slop_scan("Led migration\u2014end to end.")
        self.assertFalse(result.passed)
        self.assertTrue(any("em dash" in f["issue"].lower() for f in result.findings))

    def test_user_term_surfaces_in_composite(self) -> None:
        result = check_full_slop_scan("Led Project Falcon this quarter.", user_terms=["Project Falcon"])
        self.assertFalse(result.passed)

    def test_confidential_term_surfaces_in_composite(self) -> None:
        result = check_full_slop_scan("Shipped Project Nightingale.", confidential_terms=["Project Nightingale"])
        self.assertFalse(result.passed)


class TestLockedFactScope(unittest.TestCase):
    def setUp(self) -> None:
        self.session = Session(session_id="s", user_id="u")
        self.session.registry["F-001"] = Fact(
            id="F-001", type="metric", value="Fiber", statement="Fiber team metrics.", co_occurs_with=["F-002"]
        )
        self.session.registry["F-002"] = Fact(id="F-002", type="metric", value="2.5 minutes", statement="AHT.")

    def test_both_present_passes(self) -> None:
        result = check_locked_fact_scope("Worked on the Fiber team, reducing AHT to 2.5 minutes.", session=self.session)
        self.assertTrue(result.passed)

    def test_partner_missing_flags_high(self) -> None:
        result = check_locked_fact_scope("Worked on the Fiber team this year.", session=self.session)
        self.assertFalse(result.passed)
        self.assertEqual(result.findings[0]["severity"], "High")

    def test_neither_present_is_fine(self) -> None:
        result = check_locked_fact_scope("Led an unrelated initiative.", session=self.session)
        self.assertTrue(result.passed)

    def test_fact_with_no_co_occurrence_is_unaffected(self) -> None:
        self.session.registry["F-003"] = Fact(id="F-003", type="skill", value="Python", statement="Uses Python.")
        result = check_locked_fact_scope("Uses Python daily.", session=self.session)
        self.assertTrue(result.passed)


class TestEnumerateUnusedFoundationalBullets(unittest.TestCase):
    def test_all_used_returns_empty(self) -> None:
        result = enumerate_unused_foundational_bullets(foundational_bullet_ids=["b1", "b2"], used_bullet_ids=["b1", "b2"])
        self.assertEqual(result.data["unused_bullet_ids"], [])

    def test_unused_bullets_enumerated_exhaustively(self) -> None:
        result = enumerate_unused_foundational_bullets(
            foundational_bullet_ids=["b1", "b2", "b3", "b4"], used_bullet_ids=["b1", "b3"]
        )
        self.assertEqual(result.data["unused_bullet_ids"], ["b2", "b4"])
        self.assertEqual(result.data["unused_count"], 2)


class TestRecordFixAttempt(unittest.TestCase):
    def test_first_attempt_does_not_escalate(self) -> None:
        session = Session(session_id="s", user_id="u")
        result = record_fix_attempt("sig-1", session=session)
        self.assertTrue(result.passed)
        self.assertFalse(result.data["escalate"])
        self.assertEqual(result.data["attempt_count"], 1)

    def test_second_attempt_escalates(self) -> None:
        session = Session(session_id="s", user_id="u")
        record_fix_attempt("sig-1", session=session)
        result = record_fix_attempt("sig-1", session=session)
        self.assertFalse(result.passed)
        self.assertTrue(result.data["escalate"])
        self.assertEqual(result.data["attempt_count"], 2)

    def test_different_signatures_tracked_independently(self) -> None:
        session = Session(session_id="s", user_id="u")
        record_fix_attempt("sig-1", session=session)
        result = record_fix_attempt("sig-2", session=session)
        self.assertFalse(result.data["escalate"])


if __name__ == "__main__":
    unittest.main()
