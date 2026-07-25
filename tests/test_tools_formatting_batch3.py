import unittest

from app.tools.formatting import check_contact_fields, check_ongoing_role_date_substitution


class TestOngoingRoleDateSubstitution(unittest.TestCase):
    def test_non_ongoing_role_always_passes(self) -> None:
        result = check_ongoing_role_date_substitution("Mar 2020 - Jul 2022", is_ongoing=False)
        self.assertTrue(result.passed)

    def test_ongoing_role_matching_reference_passes(self) -> None:
        result = check_ongoing_role_date_substitution(
            "Mar 2022 - Jul 2026", is_ongoing=True, reference_date="Jul 2026"
        )
        self.assertTrue(result.passed)

    def test_ongoing_role_using_present_fails(self) -> None:
        result = check_ongoing_role_date_substitution(
            "Mar 2022 - Present", is_ongoing=True, reference_date="Jul 2026"
        )
        self.assertFalse(result.passed)

    def test_ongoing_role_with_stale_date_fails(self) -> None:
        result = check_ongoing_role_date_substitution(
            "Mar 2022 - Jan 2025", is_ongoing=True, reference_date="Jul 2026"
        )
        self.assertFalse(result.passed)
        self.assertEqual(result.findings[0]["severity"], "Critical")


class TestContactFields(unittest.TestCase):
    def test_complete_contact_passes(self) -> None:
        result = check_contact_fields("jane@example.com|555-0100|Buffalo, NY|linkedin.com/in/jane")
        self.assertTrue(result.passed)

    def test_blank_linkedin_is_fine(self) -> None:
        result = check_contact_fields("jane@example.com|555-0100|Buffalo, NY|")
        self.assertTrue(result.passed)

    def test_wrong_field_count_fails(self) -> None:
        result = check_contact_fields("jane@example.com|555-0100|Buffalo, NY")
        self.assertFalse(result.passed)
        self.assertEqual(result.findings[0]["severity"], "Critical")

    def test_missing_phone_is_critical(self) -> None:
        result = check_contact_fields("jane@example.com||Buffalo, NY|")
        self.assertFalse(result.passed)
        self.assertTrue(any("Phone" in f["issue"] for f in result.findings))

    def test_missing_location_is_critical(self) -> None:
        result = check_contact_fields("jane@example.com|555-0100||")
        self.assertFalse(result.passed)
        self.assertTrue(any("Location" in f["issue"] for f in result.findings))

    def test_malformed_email_is_critical(self) -> None:
        result = check_contact_fields("not-an-email|555-0100|Buffalo, NY|")
        self.assertFalse(result.passed)
        self.assertTrue(any("Email" in f["issue"] for f in result.findings))

    def test_street_address_as_location_is_flagged(self) -> None:
        result = check_contact_fields("jane@example.com|555-0100|123 Main Street|")
        self.assertFalse(result.passed)
        self.assertTrue(any("street address" in f["issue"] for f in result.findings))


if __name__ == "__main__":
    unittest.main()
