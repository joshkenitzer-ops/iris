import unittest

from app.session import Fact, Session
from app.tools.tailoring import check_no_invention, check_no_unauthorized_phrase_insertion


class TestNoUnauthorizedPhraseInsertion(unittest.TestCase):
    def test_phrase_not_inserted_passes(self) -> None:
        result = check_no_unauthorized_phrase_insertion(
            original_text="Led the platform team.",
            revised_text="Led the platform team through a migration.",
            flagged_phrases=["stakeholder alignment"],
        )
        self.assertTrue(result.passed)

    def test_unauthorized_insertion_fails(self) -> None:
        result = check_no_unauthorized_phrase_insertion(
            original_text="Led the platform team.",
            revised_text="Led the platform team through stakeholder alignment efforts.",
            flagged_phrases=["stakeholder alignment"],
        )
        self.assertFalse(result.passed)
        self.assertEqual(result.findings[0]["severity"], "Critical")

    def test_confirmed_insertion_passes(self) -> None:
        result = check_no_unauthorized_phrase_insertion(
            original_text="Led the platform team.",
            revised_text="Led the platform team through stakeholder alignment efforts.",
            flagged_phrases=["stakeholder alignment"],
            user_confirmed_phrases=["stakeholder alignment"],
        )
        self.assertTrue(result.passed)

    def test_phrase_already_present_is_fine(self) -> None:
        result = check_no_unauthorized_phrase_insertion(
            original_text="Led stakeholder alignment efforts.",
            revised_text="Led stakeholder alignment efforts across three teams.",
            flagged_phrases=["stakeholder alignment"],
        )
        self.assertTrue(result.passed)


class TestNoInvention(unittest.TestCase):
    def setUp(self) -> None:
        self.session = Session(session_id="s", user_id="u")
        self.session.registry["F-001"] = Fact(id="F-001", type="metric", value="2.5 minutes", statement="AHT reduced.")

    def test_span_with_valid_fact_id_passes(self) -> None:
        result = check_no_invention(
            spans=[{"text": "Reduced AHT to 2.5 minutes", "fact_id": "F-001"}], session=self.session
        )
        self.assertTrue(result.passed)

    def test_span_with_no_fact_id_fails(self) -> None:
        result = check_no_invention(spans=[{"text": "Reduced AHT dramatically", "fact_id": None}], session=self.session)
        self.assertFalse(result.passed)
        self.assertEqual(result.findings[0]["severity"], "Critical")

    def test_span_with_unknown_fact_id_fails(self) -> None:
        result = check_no_invention(spans=[{"text": "Something", "fact_id": "F-999"}], session=self.session)
        self.assertFalse(result.passed)

    def test_span_citing_superseded_fact_fails(self) -> None:
        self.session.registry["F-001"].status = "superseded"
        result = check_no_invention(spans=[{"text": "Something", "fact_id": "F-001"}], session=self.session)
        self.assertFalse(result.passed)

    def test_user_authored_span_is_exempt(self) -> None:
        result = check_no_invention(
            spans=[{"text": "Custom closing line", "fact_id": None, "user_authored": True}], session=self.session
        )
        self.assertTrue(result.passed)

    def test_mixed_spans_only_flags_the_bad_one(self) -> None:
        result = check_no_invention(
            spans=[
                {"text": "Reduced AHT to 2.5 minutes", "fact_id": "F-001"},
                {"text": "Fabricated claim", "fact_id": None},
            ],
            session=self.session,
        )
        self.assertFalse(result.passed)
        self.assertEqual(len(result.findings), 1)


if __name__ == "__main__":
    unittest.main()
