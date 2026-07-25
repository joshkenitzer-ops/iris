import unittest

from app.tools.slop_advanced import (
    check_colon_then_gerund,
    check_numerals_not_spelled_out,
    check_uniform_sentence_cadence,
)


class TestUniformSentenceCadence(unittest.TestCase):
    def test_varied_lengths_pass(self) -> None:
        text = "Led the team. Delivered a comprehensive platform migration across three regions. Shipped early."
        result = check_uniform_sentence_cadence(text)
        self.assertTrue(result.passed)

    def test_uniform_lengths_fail(self) -> None:
        text = "Led the small team well. Built the small tool fast. Shipped the small fix soon."
        result = check_uniform_sentence_cadence(text)
        self.assertFalse(result.passed)
        self.assertEqual(result.findings[0]["severity"], "Low")

    def test_too_few_sentences_trivially_passes(self) -> None:
        result = check_uniform_sentence_cadence("One sentence only.")
        self.assertTrue(result.passed)


class TestColonThenGerund(unittest.TestCase):
    def test_clean_text_passes(self) -> None:
        result = check_colon_then_gerund("Result: a 20 percent reduction in cost.")
        self.assertTrue(result.passed)

    def test_pattern_detected(self) -> None:
        result = check_colon_then_gerund("Result: Increasing efficiency across the team.")
        self.assertFalse(result.passed)


class TestNumeralsNotSpelledOut(unittest.TestCase):
    def test_numerals_pass(self) -> None:
        result = check_numerals_not_spelled_out("Reduced costs by 20 percent across 5 teams.")
        self.assertTrue(result.passed)

    def test_spelled_out_number_fails(self) -> None:
        result = check_numerals_not_spelled_out("Reduced costs by twenty percent across five teams.")
        self.assertFalse(result.passed)
        self.assertIn("twenty", result.data["spelled_out_numbers"])
        self.assertIn("five", result.data["spelled_out_numbers"])

    def test_fix_message_gives_correct_numeral(self) -> None:
        result = check_numerals_not_spelled_out("Managed a team of seven.")
        self.assertIn("7", result.findings[0]["fix"])


if __name__ == "__main__":
    unittest.main()
