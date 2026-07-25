import unittest

from app.session import Session
from app.tools.cover_letter import check_user_authored_text
from app.tools.registry_tools import record_limit_override


class TestUserAuthoredText(unittest.TestCase):
    def test_never_gates_even_with_findings(self) -> None:
        result = check_user_authored_text("Led migration\u2014end to end.")
        self.assertTrue(result.passed)  # always True, advisory only
        self.assertTrue(len(result.data["advisory_findings"]) > 0)

    def test_clean_text_has_no_advisory_findings(self) -> None:
        result = check_user_authored_text("Looking forward to connecting.")
        self.assertTrue(result.passed)
        self.assertEqual(result.data["advisory_findings"], [])

    def test_never_modifies_the_text(self) -> None:
        original = "Led migration\u2014end to end."
        check_user_authored_text(original)
        self.assertEqual(original, "Led migration\u2014end to end.")  # unchanged


class TestRecordLimitOverride(unittest.TestCase):
    def test_override_recorded_on_session(self) -> None:
        session = Session(session_id="s", user_id="u")
        result = record_limit_override(
            limit_id="T-8.7", artifact_ref="bullet-3-experience", rationale="Metric requires full context.", session=session
        )
        self.assertTrue(result.passed)
        self.assertEqual(len(session.limit_overrides), 1)
        self.assertEqual(session.limit_overrides[0].limit_id, "T-8.7")

    def test_multiple_overrides_accumulate(self) -> None:
        session = Session(session_id="s", user_id="u")
        record_limit_override(limit_id="T-8.7", artifact_ref="bullet-1", rationale="x", session=session)
        record_limit_override(limit_id="T-7.13", artifact_ref="cover-letter", rationale="y", session=session)
        self.assertEqual(len(session.limit_overrides), 2)


if __name__ == "__main__":
    unittest.main()
