import unittest

from app.gates import GateBlocked, require_amendment_confirmed, require_gap_not_silently_removed
from app.session import Session
from app.tools.tailoring import record_gap_acknowledgment


class TestRequireGapNotSilentlyRemoved(unittest.TestCase):
    def setUp(self) -> None:
        self.session = Session(session_id="s", user_id="u", fit_check_gaps=["no B2B experience"])

    def test_gap_still_present_in_final_text_passes(self) -> None:
        require_gap_not_silently_removed(self.session, "This role has no B2B experience, but strong SaaS depth.")

    def test_gap_removed_without_acknowledgment_blocks(self) -> None:
        with self.assertRaises(GateBlocked) as ctx:
            require_gap_not_silently_removed(self.session, "Strong backend and SaaS depth throughout.")
        self.assertEqual(ctx.exception.gate_id, "T-7.8")

    def test_gap_removed_with_acknowledgment_passes(self) -> None:
        record_gap_acknowledgment("no B2B experience", "user chose to omit; sales background covers it", session=self.session)
        require_gap_not_silently_removed(self.session, "Strong backend and SaaS depth throughout.")

    def test_no_gaps_at_all_passes_trivially(self) -> None:
        session = Session(session_id="s2", user_id="u")
        require_gap_not_silently_removed(session, "Anything at all.")


class TestRequireAmendmentConfirmed(unittest.TestCase):
    def test_unconfirmed_blocks(self) -> None:
        with self.assertRaises(GateBlocked) as ctx:
            require_amendment_confirmed(False)
        self.assertEqual(ctx.exception.gate_id, "T-9.5")

    def test_confirmed_passes(self) -> None:
        require_amendment_confirmed(True)  # should not raise


if __name__ == "__main__":
    unittest.main()
