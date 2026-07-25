import unittest

from app.gates import GateBlocked, require_turn_completion
from app.session import Session
from app.tools.harness_meta import (
    clear_pending_amendment,
    flag_pending_amendment,
    generate_move_item_command,
    lock_package_version,
)


class TestTurnCompletion(unittest.TestCase):
    def test_no_pending_amendment_passes(self) -> None:
        session = Session(session_id="s", user_id="u")
        require_turn_completion(session)  # should not raise

    def test_flagged_amendment_blocks_turn_completion(self) -> None:
        session = Session(session_id="s", user_id="u")
        flag_pending_amendment("closed the closing-line lock", session=session)
        with self.assertRaises(GateBlocked) as ctx:
            require_turn_completion(session)
        self.assertEqual(ctx.exception.gate_id, "T-9.6")

    def test_clearing_after_commit_passes(self) -> None:
        session = Session(session_id="s", user_id="u")
        flag_pending_amendment("closed the closing-line lock", session=session)
        clear_pending_amendment(session=session)
        require_turn_completion(session)  # should not raise


class TestLockPackageVersion(unittest.TestCase):
    def test_first_lock_is_version_one(self) -> None:
        session = Session(session_id="s", user_id="u")
        result = lock_package_version("resume-acme-pm", session=session)
        self.assertEqual(result.data["version"], 1)

    def test_second_lock_increments(self) -> None:
        session = Session(session_id="s", user_id="u")
        lock_package_version("resume-acme-pm", session=session)
        result = lock_package_version("resume-acme-pm", session=session)
        self.assertEqual(result.data["version"], 2)

    def test_different_artifacts_tracked_independently(self) -> None:
        session = Session(session_id="s", user_id="u")
        lock_package_version("resume-acme-pm", session=session)
        result = lock_package_version("coverletter-acme-pm", session=session)
        self.assertEqual(result.data["version"], 1)


class TestGenerateMoveItemCommand(unittest.TestCase):
    def test_produces_expected_shape(self) -> None:
        result = generate_move_item_command("Kenitzer_Josh_Resume_Acme_PM_v1.docx", "C:\\dev\\iris\\outputs")
        command = result.data["command"]
        self.assertIn("Move-Item", command)
        self.assertIn("$HOME\\Downloads\\Kenitzer_Josh_Resume_Acme_PM_v1.docx", command)
        self.assertIn("C:\\dev\\iris\\outputs\\Kenitzer_Josh_Resume_Acme_PM_v1.docx", command)
        self.assertIn("-Force", command)


if __name__ == "__main__":
    unittest.main()
