import unittest

from app.tools.consistency import check_figures_against_foundational


class TestCheckFiguresAgainstFoundational(unittest.TestCase):
    def test_all_figures_traceable_passes(self) -> None:
        result = check_figures_against_foundational(
            tailored_text="Reduced AHT to 2.5 minutes for 150 managers.",
            foundational_text="AHT dropped to 2.5 minutes across 150 managers surveyed.",
        )
        self.assertTrue(result.passed)

    def test_untraceable_figure_is_critical(self) -> None:
        result = check_figures_against_foundational(
            tailored_text="Reduced AHT to 2 minutes.",
            foundational_text="AHT dropped to 2.5 minutes.",
        )
        self.assertFalse(result.passed)
        self.assertIn("2", result.data["untraceable_figures"])
        self.assertEqual(result.findings[0]["severity"], "Critical")

    def test_no_figures_in_tailored_passes_trivially(self) -> None:
        result = check_figures_against_foundational(tailored_text="No numbers here.", foundational_text="AHT was 2.5 minutes.")
        self.assertTrue(result.passed)


if __name__ == "__main__":
    unittest.main()
