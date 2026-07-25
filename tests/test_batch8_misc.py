import unittest

from app.session import Fact, Session
from app.tools.final_review import (
    check_results_have_explicit_verdict,
    check_tl_run_on_and_jargon,
    nominate_added_clauses,
)
from app.tools.profile import check_facts_traceable_to_master
from app.tools.registry_tools import get_inventory_section_facts


class TestFactsTraceableToMaster(unittest.TestCase):
    def setUp(self) -> None:
        self.session = Session(session_id="s", user_id="u")
        self.session.registry["F-001"] = Fact(id="F-001", type="metric", value="2.5 minutes", statement="AHT.")

    def test_fact_present_in_master_passes(self) -> None:
        result = check_facts_traceable_to_master("The AHT was reduced to 2.5 minutes.", session=self.session)
        self.assertTrue(result.passed)

    def test_fact_missing_from_master_flags_medium(self) -> None:
        result = check_facts_traceable_to_master("Nothing about AHT here.", session=self.session)
        self.assertFalse(result.passed)
        self.assertEqual(result.findings[0]["severity"], "Medium")

    def test_approved_variant_counts_as_traceable(self) -> None:
        self.session.registry["F-001"].approve_variant("two and a half minutes")
        result = check_facts_traceable_to_master("Cut it to two and a half minutes.", session=self.session)
        self.assertTrue(result.passed)


class TestInventorySectionFacts(unittest.TestCase):
    def setUp(self) -> None:
        self.session = Session(session_id="s", user_id="u")
        self.session.registry["F-001"] = Fact(id="F-001", type="skill", value="Python", statement="x", role_ref="role-1")
        self.session.registry["F-002"] = Fact(id="F-002", type="metric", value="5", statement="y", role_ref="role-2")

    def test_filters_by_role_ref(self) -> None:
        result = get_inventory_section_facts("role-1", session=self.session)
        self.assertEqual(result.data["count"], 1)
        self.assertEqual(result.data["facts"][0]["id"], "F-001")

    def test_filters_by_type(self) -> None:
        result = get_inventory_section_facts("metric", session=self.session)
        self.assertEqual(result.data["count"], 1)
        self.assertEqual(result.data["facts"][0]["id"], "F-002")

    def test_no_match_returns_empty(self) -> None:
        result = get_inventory_section_facts("role-99", session=self.session)
        self.assertEqual(result.data["count"], 0)


class TestNominateAddedClauses(unittest.TestCase):
    def test_no_additions_passes(self) -> None:
        result = nominate_added_clauses("Led the platform migration.", "Led the platform migration.")
        self.assertTrue(result.passed)

    def test_added_clause_nominated(self) -> None:
        result = nominate_added_clauses(
            "Led the platform migration.", "Led the platform migration across three global regions."
        )
        self.assertFalse(result.passed)
        self.assertTrue(len(result.data["added_spans"]) > 0)


class TestTlRunOnAndJargon(unittest.TestCase):
    def test_clean_text_passes(self) -> None:
        result = check_tl_run_on_and_jargon("Led the migration. Cut costs by 20 percent.")
        self.assertTrue(result.passed)

    def test_run_on_surfaces(self) -> None:
        long_sentence = " ".join(["word"] * 35) + "."
        result = check_tl_run_on_and_jargon(long_sentence)
        self.assertFalse(result.passed)

    def test_jargon_surfaces(self) -> None:
        result = check_tl_run_on_and_jargon("Worked on Project Falcon.", known_terms=["Project Falcon"])
        self.assertFalse(result.passed)


class TestResultsHaveExplicitVerdict(unittest.TestCase):
    def test_all_explicit_passes(self) -> None:
        result = check_results_have_explicit_verdict([{"passed": True}, {"passed": False}])
        self.assertTrue(result.passed)

    def test_missing_verdict_fails(self) -> None:
        result = check_results_have_explicit_verdict([{"passed": True}, {"data": "no verdict here"}])
        self.assertFalse(result.passed)
        self.assertEqual(result.findings[0]["severity"], "Critical")

    def test_non_boolean_verdict_fails(self) -> None:
        result = check_results_have_explicit_verdict([{"passed": "yes"}])
        self.assertFalse(result.passed)


if __name__ == "__main__":
    unittest.main()
