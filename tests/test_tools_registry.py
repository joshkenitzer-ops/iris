import unittest

from app.session import Fact, Session
from app.tools.registry_tools import check_value_against_registry, validate_facts_for_locking


class TestValidateFactsForLocking(unittest.TestCase):
    def test_complete_facts_pass(self) -> None:
        facts = [{"type": "metric", "value": "2.5 minutes", "statement": "Reduced AHT to 2.5 minutes."}]
        result = validate_facts_for_locking(facts)
        self.assertTrue(result.passed)
        self.assertEqual(result.data["fact_count"], 1)

    def test_missing_field_fails(self) -> None:
        facts = [{"type": "metric", "value": "2.5 minutes"}]  # no statement
        result = validate_facts_for_locking(facts)
        self.assertFalse(result.passed)
        self.assertIn("statement", result.findings[0]["issue"])


class TestCheckValueAgainstRegistry(unittest.TestCase):
    def setUp(self) -> None:
        self.session = Session(session_id="s1", user_id="u1")
        self.session.registry["F-001"] = Fact(
            id="F-001", type="metric", value="2.5 minutes", statement="AHT reduced to 2.5 minutes."
        )
        self.session.registry["F-002"] = Fact(
            id="F-002",
            type="metric",
            value="2,680 respondents",
            statement="Survey of 2,680 respondents.",
            status="superseded",
            supersedes=None,
        )

    def test_exact_match_passes(self) -> None:
        result = check_value_against_registry("F-001", "2.5 minutes", session=self.session)
        self.assertTrue(result.passed)

    def test_altered_value_is_critical(self) -> None:
        result = check_value_against_registry("F-001", "2 minutes", session=self.session)
        self.assertFalse(result.passed)
        self.assertEqual(result.findings[0]["severity"], "Critical")

    def test_approved_variant_passes(self) -> None:
        self.session.registry["F-001"].approve_variant("two and a half minutes")
        result = check_value_against_registry("F-001", "two and a half minutes", session=self.session)
        self.assertTrue(result.passed)

    def test_unapproved_variant_fails(self) -> None:
        result = check_value_against_registry("F-001", "two and a half minutes", session=self.session)
        self.assertFalse(result.passed)

    def test_unknown_fact_id_fails(self) -> None:
        result = check_value_against_registry("F-999", "anything", session=self.session)
        self.assertFalse(result.passed)
        self.assertIn("No registry entry", result.findings[0]["issue"])

    def test_superseded_fact_fails(self) -> None:
        result = check_value_against_registry("F-002", "2,680 respondents", session=self.session)
        self.assertFalse(result.passed)
        self.assertIn("superseded", result.findings[0]["issue"])

    def test_model_cannot_supply_its_own_fact_set(self) -> None:
        """The tool's input_schema only accepts fact_id and
        claimed_value, there is no field for a fact list. This test
        documents that the function signature itself, not just the
        schema, refuses a third argument, since needs_session tools
        get their registry from the harness, never from the caller."""
        with self.assertRaises(TypeError):
            check_value_against_registry(
                "F-001", "2 minutes", session=self.session, active_facts=[]
            )


if __name__ == "__main__":
    unittest.main()
