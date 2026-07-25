import unittest

from app.tools.intake import (
    check_career_inventory_schema,
    find_near_duplicate_candidates,
    route_low_confidence_to_manual_review,
    score_extraction_confidence,
)


class TestScoreExtractionConfidence(unittest.TestCase):
    def test_clean_extraction_passes(self) -> None:
        result = score_extraction_confidence(
            ocr_confidence=0.98,
            replacement_char_ratio=0.0,
            role_blocks_with_dates=4,
            date_parse_failure_ratio=0.0,
        )
        self.assertTrue(result.passed)
        self.assertEqual(result.data["tripped_signals"], [])

    def test_low_ocr_confidence_trips(self) -> None:
        result = score_extraction_confidence(
            ocr_confidence=0.5,
            replacement_char_ratio=0.0,
            role_blocks_with_dates=4,
            date_parse_failure_ratio=0.0,
        )
        self.assertFalse(result.passed)
        self.assertTrue(any("ocr_confidence" in s for s in result.data["tripped_signals"]))

    def test_too_few_role_blocks_trips(self) -> None:
        result = score_extraction_confidence(
            ocr_confidence=0.98,
            replacement_char_ratio=0.0,
            role_blocks_with_dates=1,
            date_parse_failure_ratio=0.0,
        )
        self.assertFalse(result.passed)

    def test_multiple_signals_all_reported(self) -> None:
        result = score_extraction_confidence(
            ocr_confidence=0.1,
            replacement_char_ratio=0.5,
            role_blocks_with_dates=0,
            date_parse_failure_ratio=0.9,
        )
        self.assertFalse(result.passed)
        self.assertEqual(len(result.data["tripped_signals"]), 4)


class TestRouteLowConfidence(unittest.TestCase):
    def test_passed_extraction_does_not_route(self) -> None:
        result = route_low_confidence_to_manual_review(extraction_passed=True)
        self.assertTrue(result.passed)

    def test_failed_extraction_routes(self) -> None:
        result = route_low_confidence_to_manual_review(
            extraction_passed=False, tripped_signals=["ocr_confidence low"]
        )
        self.assertFalse(result.passed)
        self.assertEqual(result.data["tripped_signals"], ["ocr_confidence low"])


class TestCareerInventorySchema(unittest.TestCase):
    def test_all_required_present_passes(self) -> None:
        result = check_career_inventory_schema(
            {"NAME": "Jane Doe", "CONTACT": "j@x.com|555|Buffalo, NY|", "SKILLS": "Python", "EXPERIENCE": "..."}
        )
        self.assertTrue(result.passed)

    def test_missing_required_section_is_critical(self) -> None:
        result = check_career_inventory_schema({"NAME": "Jane Doe"})
        self.assertFalse(result.passed)
        critical = [f for f in result.findings if f["severity"] == "Critical"]
        self.assertEqual(len(critical), 3)  # CONTACT, SKILLS, EXPERIENCE missing

    def test_unknown_section_flagged(self) -> None:
        result = check_career_inventory_schema(
            {
                "NAME": "Jane Doe",
                "CONTACT": "j@x.com|555|Buffalo, NY|",
                "SKILLS": "Python",
                "EXPERIENCE": "...",
                "HOBBIES": "Chess",
            }
        )
        self.assertFalse(result.passed)
        self.assertIn("HOBBIES", result.data["unknown_sections"])

    def test_generated_section_supplied_directly_is_low_severity_note(self) -> None:
        result = check_career_inventory_schema(
            {
                "NAME": "Jane Doe",
                "CONTACT": "j@x.com|555|Buffalo, NY|",
                "SKILLS": "Python",
                "EXPERIENCE": "...",
                "HEADLINE": "Senior PM",
            }
        )
        self.assertFalse(result.passed)  # not Critical, but not silently passed either
        self.assertTrue(any(f["severity"] == "Low" for f in result.findings))


class TestNearDuplicateCandidates(unittest.TestCase):
    def test_distinct_items_pass(self) -> None:
        result = find_near_duplicate_candidates(["Led migration to AWS.", "Managed a team of five."])
        self.assertTrue(result.passed)

    def test_near_identical_items_nominated(self) -> None:
        result = find_near_duplicate_candidates(
            ["Led migration of billing service to AWS.", "Led migration of the billing service to AWS."]
        )
        self.assertFalse(result.passed)
        self.assertEqual(len(result.data["candidates"]), 1)

    def test_threshold_is_respected(self) -> None:
        result = find_near_duplicate_candidates(
            ["Led migration to AWS.", "Managed onboarding redesign."], threshold=0.99
        )
        self.assertTrue(result.passed)


if __name__ == "__main__":
    unittest.main()
