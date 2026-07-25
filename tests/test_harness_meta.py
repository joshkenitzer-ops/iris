import unittest

from app.session import Session
from app.tools.harness_meta import check_batch_state, generate_amendment_diff


class TestGenerateAmendmentDiff(unittest.TestCase):
    def test_identical_text_produces_no_changes(self) -> None:
        result = generate_amendment_diff("same text\n", "same text\n")
        self.assertFalse(result.data["changed"])

    def test_changed_text_produces_a_diff(self) -> None:
        result = generate_amendment_diff("old line\n", "new line\n", label="iris-spec.md")
        self.assertTrue(result.data["changed"])
        self.assertIn("-old line", result.data["diff"])
        self.assertIn("+new line", result.data["diff"])
        self.assertIn("iris-spec.md", result.data["diff"])


class TestCheckBatchState(unittest.TestCase):
    def test_no_active_batch_opens_cleanly(self) -> None:
        session = Session(session_id="s", user_id="u")
        result = check_batch_state("batch-1", session=session)
        self.assertTrue(result.passed)
        self.assertEqual(session.active_batch_id, "batch-1")

    def test_reopening_same_batch_is_fine(self) -> None:
        session = Session(session_id="s", user_id="u", active_batch_id="batch-1")
        result = check_batch_state("batch-1", session=session)
        self.assertTrue(result.passed)

    def test_starting_new_batch_while_one_open_fails(self) -> None:
        session = Session(session_id="s", user_id="u", active_batch_id="batch-1")
        result = check_batch_state("batch-2", session=session)
        self.assertFalse(result.passed)
        self.assertEqual(result.findings[0]["severity"], "High")


if __name__ == "__main__":
    unittest.main()
