import unittest

from app.gates import GateBlocked
from app.session import Fact, Session
from app.tools.foundational_build import (
    check_headline_placement,
    check_headline_skills_backed,
    check_role_summary_length,
    detect_internal_project_names,
    require_value_immutable,
)


class TestRoleSummaryLength(unittest.TestCase):
    def test_one_sentence_passes(self) -> None:
        result = check_role_summary_length("Led the platform team through a major migration.")
        self.assertTrue(result.passed)

    def test_two_sentences_passes(self) -> None:
        result = check_role_summary_length("Led the platform team. Delivered the migration on schedule.")
        self.assertTrue(result.passed)

    def test_three_sentences_fails(self) -> None:
        result = check_role_summary_length("One. Two. Three.")
        self.assertFalse(result.passed)
        self.assertEqual(result.data["sentence_count"], 3)

    def test_empty_fails(self) -> None:
        result = check_role_summary_length("   ")
        self.assertFalse(result.passed)


class TestHeadlineSkillsBacked(unittest.TestCase):
    def setUp(self) -> None:
        self.session = Session(session_id="s", user_id="u")
        self.session.registry["F-001"] = Fact(id="F-001", type="skill", value="Python", statement="Uses Python.")

    def test_backed_skill_passes(self) -> None:
        result = check_headline_skills_backed(["Python"], session=self.session)
        self.assertTrue(result.passed)

    def test_unbacked_skill_is_critical(self) -> None:
        result = check_headline_skills_backed(["Rust"], session=self.session)
        self.assertFalse(result.passed)
        self.assertEqual(result.findings[0]["severity"], "Critical")

    def test_case_insensitive_match(self) -> None:
        result = check_headline_skills_backed(["python"], session=self.session)
        self.assertTrue(result.passed)

    def test_variant_counts_as_backed(self) -> None:
        self.session.registry["F-001"].approve_variant("Python programming")
        result = check_headline_skills_backed(["Python programming"], session=self.session)
        self.assertTrue(result.passed)


class TestHeadlinePlacement(unittest.TestCase):
    def test_correct_order_passes(self) -> None:
        result = check_headline_placement(["NAME", "HEADLINE", "CONTACT", "SUMMARY"])
        self.assertTrue(result.passed)

    def test_headline_after_contact_fails(self) -> None:
        result = check_headline_placement(["NAME", "CONTACT", "HEADLINE", "SUMMARY"])
        self.assertFalse(result.passed)

    def test_missing_section_fails(self) -> None:
        result = check_headline_placement(["NAME", "SUMMARY"])
        self.assertFalse(result.passed)
        self.assertEqual(result.findings[0]["severity"], "Critical")


class TestValueImmutability(unittest.TestCase):
    def setUp(self) -> None:
        self.session = Session(session_id="s", user_id="u")
        self.session.registry["F-001"] = Fact(id="F-001", type="metric", value="2.5 minutes", statement="AHT reduced.")

    def test_new_fact_id_is_unaffected(self) -> None:
        require_value_immutable(self.session, "F-999", "anything")  # should not raise

    def test_same_value_is_fine(self) -> None:
        require_value_immutable(self.session, "F-001", "2.5 minutes")  # should not raise

    def test_approved_variant_is_fine(self) -> None:
        self.session.registry["F-001"].approve_variant("two and a half minutes")
        require_value_immutable(self.session, "F-001", "two and a half minutes")  # should not raise

    def test_direct_overwrite_attempt_blocks(self) -> None:
        with self.assertRaises(GateBlocked) as ctx:
            require_value_immutable(self.session, "F-001", "2 minutes")
        self.assertEqual(ctx.exception.gate_id, "T-2.9a")

    def test_superseded_fact_is_unprotected(self) -> None:
        self.session.registry["F-001"].status = "superseded"
        require_value_immutable(self.session, "F-001", "anything")  # should not raise


class TestDetectInternalProjectNames(unittest.TestCase):
    def test_no_names_present_passes(self) -> None:
        result = detect_internal_project_names("Led the onboarding redesign.", known_internal_names=["Project Falcon"])
        self.assertTrue(result.passed)

    def test_name_detected_is_low_severity_informational(self) -> None:
        result = detect_internal_project_names(
            "Led Project Falcon to completion.", known_internal_names=["Project Falcon"]
        )
        self.assertFalse(result.passed)
        self.assertEqual(result.findings[0]["severity"], "Low")


if __name__ == "__main__":
    unittest.main()
