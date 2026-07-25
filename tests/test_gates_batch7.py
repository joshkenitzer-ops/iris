import unittest

from app.gates import GateBlocked, require_fit_check_completed, require_no_fabricated_compensation_range
from app.session import Session


class TestRequireFitCheckCompleted(unittest.TestCase):
    def test_incomplete_fit_check_blocks(self) -> None:
        session = Session(session_id="s", user_id="u")
        with self.assertRaises(GateBlocked) as ctx:
            require_fit_check_completed(session)
        self.assertEqual(ctx.exception.gate_id, "T-5.1")

    def test_completed_fit_check_passes(self) -> None:
        session = Session(session_id="s", user_id="u", fit_check_completed=True)
        require_fit_check_completed(session)  # should not raise


class TestRequireNoFabricatedCompensationRange(unittest.TestCase):
    def test_successful_search_with_range_is_fine(self) -> None:
        require_no_fabricated_compensation_range(search_succeeded=True, presented_text="$120,000 - $140,000")

    def test_failed_search_with_no_range_is_fine(self) -> None:
        require_no_fabricated_compensation_range(
            search_succeeded=False, presented_text="Compensation could not be reliably estimated for this role."
        )

    def test_failed_search_with_range_blocks(self) -> None:
        with self.assertRaises(GateBlocked) as ctx:
            require_no_fabricated_compensation_range(search_succeeded=False, presented_text="$120,000 - $140,000")
        self.assertEqual(ctx.exception.gate_id, "T-5.8")

    def test_failed_search_with_to_phrasing_range_blocks(self) -> None:
        with self.assertRaises(GateBlocked):
            require_no_fabricated_compensation_range(search_succeeded=False, presented_text="$120,000 to $140,000")


if __name__ == "__main__":
    unittest.main()
