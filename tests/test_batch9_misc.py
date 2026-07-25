import threading
import unittest

from app.session import Session, SessionNotFoundError, SessionStore
from app.tools.master_build import check_headline_title_match, check_summary_bullet_count
from app.tools.registry_tools import extract_facts_into_registry
from app.tools.tailoring import ingest_job_description
from app.tools.final_review import run_ai_writing_detection_signals


class TestExtractFactsIntoRegistry(unittest.TestCase):
    def setUp(self) -> None:
        self.session = Session(session_id="s", user_id="u")

    def test_new_fact_gets_sequential_id(self) -> None:
        result = extract_facts_into_registry(
            [{"type": "metric", "value": "20%", "statement": "Cut cost by 20%."}], session=self.session
        )
        self.assertTrue(result.passed)
        self.assertEqual(result.data["fact_ids"], ["F-001"])
        self.assertEqual(self.session.registry["F-001"].value, "20%")

    def test_multiple_new_facts_increment_sequentially(self) -> None:
        result = extract_facts_into_registry(
            [
                {"type": "skill", "value": "Python", "statement": "x"},
                {"type": "skill", "value": "SQL", "statement": "y"},
            ],
            session=self.session,
        )
        self.assertEqual(result.data["fact_ids"], ["F-001", "F-002"])

    def test_matching_value_on_existing_id_is_a_no_op_write(self) -> None:
        extract_facts_into_registry([{"type": "metric", "value": "20%", "statement": "x"}], session=self.session)
        result = extract_facts_into_registry(
            [{"id": "F-001", "type": "metric", "value": "20%", "statement": "x"}], session=self.session
        )
        self.assertTrue(result.passed)

    def test_conflicting_value_on_existing_id_is_blocked_not_overwritten(self) -> None:
        extract_facts_into_registry([{"type": "metric", "value": "20%", "statement": "x"}], session=self.session)
        result = extract_facts_into_registry(
            [{"id": "F-001", "type": "metric", "value": "25%", "statement": "x"}], session=self.session
        )
        self.assertFalse(result.passed)
        self.assertEqual(result.findings[0]["severity"], "Critical")
        self.assertEqual(self.session.registry["F-001"].value, "20%")

    def test_shape_invalid_batch_never_writes_anything(self) -> None:
        result = extract_facts_into_registry([{"type": "metric", "statement": "missing value"}], session=self.session)
        self.assertFalse(result.passed)
        self.assertEqual(len(self.session.registry), 0)


class TestIngestJobDescription(unittest.TestCase):
    def setUp(self) -> None:
        self.session = Session(session_id="s", user_id="u", fit_check_completed=True, fit_check_gaps=["no B2B"])

    def test_empty_text_fails(self) -> None:
        result = ingest_job_description("   ", session=self.session)
        self.assertFalse(result.passed)

    def test_valid_text_resets_fit_check_state(self) -> None:
        result = ingest_job_description("We need a great engineer.", session=self.session)
        self.assertTrue(result.passed)
        self.assertFalse(self.session.fit_check_completed)
        self.assertEqual(self.session.fit_check_gaps, [])
        self.assertIsNotNone(self.session.jd_fingerprint)

    def test_same_text_gives_same_fingerprint(self) -> None:
        r1 = ingest_job_description("Same posting text.", session=self.session)
        r2 = ingest_job_description("Same posting text.", session=self.session)
        self.assertEqual(r1.data["jd_fingerprint"], r2.data["jd_fingerprint"])


class TestCheckSummaryBulletCount(unittest.TestCase):
    def test_three_bullets_passes(self) -> None:
        self.assertTrue(check_summary_bullet_count(["a", "b", "c"]).passed)

    def test_five_bullets_passes(self) -> None:
        self.assertTrue(check_summary_bullet_count(["a", "b", "c", "d", "e"]).passed)

    def test_two_bullets_fails(self) -> None:
        self.assertFalse(check_summary_bullet_count(["a", "b"]).passed)

    def test_six_bullets_fails(self) -> None:
        self.assertFalse(check_summary_bullet_count(["a", "b", "c", "d", "e", "f"]).passed)

    def test_blank_bullets_are_not_counted(self) -> None:
        result = check_summary_bullet_count(["a", "b", "c", "  ", ""])
        self.assertEqual(result.data["bullet_count"], 3)


class TestCheckHeadlineTitleMatch(unittest.TestCase):
    def test_exact_title_present_passes(self) -> None:
        result = check_headline_title_match("Senior Backend Engineer | Python, AWS", "Senior Backend Engineer")
        self.assertTrue(result.passed)

    def test_case_insensitive_match_passes(self) -> None:
        result = check_headline_title_match("senior backend engineer with 8 years", "Senior Backend Engineer")
        self.assertTrue(result.passed)

    def test_missing_title_fails(self) -> None:
        result = check_headline_title_match("Backend Engineer", "Senior Backend Engineer")
        self.assertFalse(result.passed)

    def test_empty_posting_title_fails(self) -> None:
        result = check_headline_title_match("Backend Engineer", "  ")
        self.assertFalse(result.passed)


class TestRunAiWritingDetectionSignals(unittest.TestCase):
    def test_empty_text_returns_no_signals(self) -> None:
        result = run_ai_writing_detection_signals("")
        self.assertTrue(result.passed)
        self.assertEqual(result.data["signals"], {})

    def test_never_gates_even_when_flagged(self) -> None:
        uniform = (
            "The team delivered the project. The team delivered the goal. "
            "The team delivered the result. The team delivered the outcome."
        )
        result = run_ai_writing_detection_signals(uniform)
        self.assertTrue(result.passed)  # informational only, never blocks

    def test_uniform_low_diversity_text_surfaces_a_low_severity_signal(self) -> None:
        uniform = (
            "The team delivered the project. The team delivered the goal. "
            "The team delivered the result. The team delivered the outcome."
        )
        result = run_ai_writing_detection_signals(uniform)
        self.assertEqual(len(result.findings), 1)
        self.assertEqual(result.findings[0]["severity"], "Low")
        self.assertEqual(result.data["signals"]["sentence_length_variance"], 0.0)

    def test_varied_natural_text_does_not_surface_a_signal(self) -> None:
        varied = (
            "Cats sleep most of the day, curled in patches of afternoon sun. "
            "Rain rarely stops the neighborhood kids from playing outside, and "
            "their laughter echoes across the block whenever a storm finally "
            "breaks. Quiet mornings suit her best. She writes long letters "
            "nobody reads anymore, sealing them in envelopes destined for a "
            "bottom desk drawer near the window facing the old maple tree."
        )
        result = run_ai_writing_detection_signals(varied)
        self.assertEqual(len(result.findings), 0)


class TestSessionStoreLogoutAndConcurrency(unittest.TestCase):
    def setUp(self) -> None:
        self.store = SessionStore()

    def test_delete_removes_session(self) -> None:
        session = self.store.create("josh")
        self.store.delete("josh", session.session_id)
        with self.assertRaises(SessionNotFoundError):
            self.store.get("josh", session.session_id)

    def test_delete_nonexistent_session_raises(self) -> None:
        with self.assertRaises(SessionNotFoundError):
            self.store.delete("josh", "does-not-exist")

    def test_delete_with_wrong_user_id_raises_the_same_error(self) -> None:
        """T-9.12: a delete under the wrong user_id must not distinguish
        itself from a nonexistent session_id, same isolation rule as get()."""
        session = self.store.create("alice")
        with self.assertRaises(SessionNotFoundError):
            self.store.delete("bob", session.session_id)
        # and it's still there for the real owner
        self.assertIsNotNone(self.store.get("alice", session.session_id))

    def test_concurrent_creates_all_succeed_with_unique_ids(self) -> None:
        results = []

        def worker(i: int) -> None:
            session = self.store.create(f"user{i}")
            results.append(session.session_id)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(results), 50)
        self.assertEqual(len(set(results)), 50)


if __name__ == "__main__":
    unittest.main()
