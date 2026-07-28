"""
Regression coverage for the incomplete profile-import path (2026-07-27).

export_iris_profile always serialized the registry and import_iris_profile
always validated it, but nothing ever wrote it back onto the session: the
only writer anywhere was registry_tools.lock_fact. So "pick up where I
left off" restored dismissed findings and nothing else, left the registry
empty, and T-5.2 then blocked Fit Check. The tool description meanwhile
told the model the import saved "a full re-audit", which the model would
act on.
"""

import base64
import unittest

import app.tools  # noqa: F401  (registers tools)
from app.gates import GateBlocked, require_registry_populated
from app.session import Fact, Session
from app.tools.profile import (
    check_profile_integrity,
    export_iris_profile,
    import_iris_profile,
    restore_registry_from_profile,
)


def _profile_markdown(session: Session) -> str:
    result = export_iris_profile("Kenitzer_Joshua_IrisProfile.md", session=session)
    rendered = session.get_rendered_file(result.data["file_id"])
    return base64.b64decode(rendered.data_base64).decode("utf-8")


def _seeded_session() -> Session:
    session = Session(session_id="s", user_id="u")
    session.registry["F1"] = Fact(id="F1", type="metric", value="19 years", statement="19 years at Google")
    session.registry["F2"] = Fact(id="F2", type="claim", value="FSE 2025", statement="Presented at FSE 2025")
    session.master_fingerprint = "abc123"
    return session


class TestFullProfileRoundTrip(unittest.TestCase):
    def test_a_returning_user_gets_their_registry_back(self) -> None:
        original = _seeded_session()
        markdown = _profile_markdown(original)

        returning = Session(session_id="s2", user_id="u")
        payload = import_iris_profile(check_profile_integrity(markdown).data["json_body"]).data["payload"]
        result = restore_registry_from_profile(
            payload["registry"], session=returning, master_fingerprint=payload["master_fingerprint"]
        )

        self.assertTrue(result.passed)
        self.assertEqual(result.data["restored_count"], 2)
        self.assertEqual(len(returning.active_facts()), 2)
        self.assertEqual(returning.registry["F1"].value, "19 years")

    def test_restored_session_is_no_longer_blocked_from_fit_check(self) -> None:
        """The user-visible consequence. Before the restore step existed
        this raised, which is where a returning user actually hit the
        wall."""
        original = _seeded_session()
        markdown = _profile_markdown(original)
        returning = Session(session_id="s2", user_id="u")

        with self.assertRaises(GateBlocked):
            require_registry_populated(returning)

        payload = import_iris_profile(check_profile_integrity(markdown).data["json_body"]).data["payload"]
        restore_registry_from_profile(payload["registry"], session=returning)
        require_registry_populated(returning)  # no longer raises

    def test_master_fingerprint_travels_with_the_facts(self) -> None:
        returning = Session(session_id="s2", user_id="u")
        restore_registry_from_profile([], session=returning, master_fingerprint="abc123")
        self.assertEqual(returning.master_fingerprint, "abc123")


class TestRestoreRefusesToClobber(unittest.TestCase):
    def test_will_not_overwrite_a_session_that_already_has_facts(self) -> None:
        session = _seeded_session()
        result = restore_registry_from_profile(
            [{"id": "X", "type": "claim", "value": "v", "statement": "s"}], session=session
        )
        self.assertFalse(result.passed)
        self.assertEqual(len(session.active_facts()), 2)  # untouched
        self.assertNotIn("X", session.registry)


class TestRestoreHandlesBadEntries(unittest.TestCase):
    def setUp(self) -> None:
        self.session = Session(session_id="s", user_id="u")

    def test_entry_missing_required_fields_is_skipped_not_fatal(self) -> None:
        result = restore_registry_from_profile(
            [
                {"id": "GOOD", "type": "metric", "value": "19 years", "statement": "ok"},
                {"id": "BAD", "type": "metric"},  # no value/statement
            ],
            session=self.session,
        )
        self.assertEqual(result.data["restored_count"], 1)
        self.assertEqual(result.data["skipped_count"], 1)
        self.assertIn("GOOD", self.session.registry)
        self.assertNotIn("BAD", self.session.registry)

    def test_non_object_entry_is_skipped_not_fatal(self) -> None:
        result = restore_registry_from_profile(["nonsense", 42], session=self.session)
        self.assertEqual(result.data["restored_count"], 0)
        self.assertEqual(result.data["skipped_count"], 2)

    def test_unknown_future_field_does_not_lose_the_whole_import(self) -> None:
        """A profile written by a newer harness should degrade to the
        fields this version understands, not raise TypeError and discard
        everything."""
        result = restore_registry_from_profile(
            [{"id": "F1", "type": "metric", "value": "v", "statement": "s", "field_from_the_future": True}],
            session=self.session,
        )
        self.assertTrue(result.passed)
        self.assertIn("F1", self.session.registry)

    def test_variants_and_status_survive_the_round_trip(self) -> None:
        source = Session(session_id="s", user_id="u")
        fact = Fact(id="F1", type="metric", value="19 years", statement="s")
        fact.approve_variant("nineteen years")
        source.registry["F1"] = fact
        markdown = _profile_markdown(source)

        returning = Session(session_id="s2", user_id="u")
        payload = import_iris_profile(check_profile_integrity(markdown).data["json_body"]).data["payload"]
        restore_registry_from_profile(payload["registry"], session=returning)

        self.assertIn("nineteen years", returning.registry["F1"].variants)
        self.assertEqual(returning.registry["F1"].status, "active")


if __name__ == "__main__":
    unittest.main()
