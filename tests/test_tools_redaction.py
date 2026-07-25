import unittest

from app.tools.redaction import redact_colleague_names


class TestRedactColleagueNames(unittest.TestCase):
    def test_single_name_replaced(self) -> None:
        result = redact_colleague_names("Jane Smith approved the plan.", identified_names=["Jane Smith"])
        self.assertTrue(result.passed)
        self.assertNotIn("Jane Smith", result.data["redacted_text"])
        self.assertIn("Colleague A", result.data["redacted_text"])

    def test_case_insensitive_replacement(self) -> None:
        result = redact_colleague_names("jane smith signed off.", identified_names=["Jane Smith"])
        self.assertTrue(result.passed)
        self.assertNotIn("smith", result.data["redacted_text"].lower())

    def test_multiple_names_get_distinct_labels(self) -> None:
        result = redact_colleague_names(
            "Jane Smith and Bob Jones both approved.", identified_names=["Jane Smith", "Bob Jones"]
        )
        self.assertTrue(result.passed)
        labels = set(result.data["label_map"].values())
        self.assertEqual(len(labels), 2)

    def test_substring_name_ordering_does_not_leak_fragment(self) -> None:
        """The exact failure mode the longest-first ordering exists to
        prevent: 'Jane' is a substring of 'Jane Smith'. If 'Jane' were
        substituted first, 'Jane Smith' would become 'Colleague X
        Smith', leaking the surname."""
        result = redact_colleague_names(
            "Jane Smith approved it; Jane later confirmed.",
            identified_names=["Jane", "Jane Smith"],
        )
        self.assertTrue(result.passed)
        self.assertNotIn("Smith", result.data["redacted_text"])
        self.assertNotIn("Jane", result.data["redacted_text"])

    def test_duplicate_names_in_input_deduped(self) -> None:
        result = redact_colleague_names("Jane Smith said so.", identified_names=["Jane Smith", "Jane Smith"])
        self.assertEqual(len(result.data["label_map"]), 1)

    def test_no_names_present_passes_unchanged(self) -> None:
        result = redact_colleague_names("Led the migration alone.", identified_names=["Jane Smith"])
        self.assertTrue(result.passed)
        self.assertEqual(result.data["redacted_text"], "Led the migration alone.")


if __name__ == "__main__":
    unittest.main()
