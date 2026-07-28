"""Coverage for per-turn token accounting (app/usage.py) and for its
reachability through the real streaming path.

The reachability half matters as much as the arithmetic half. A usage
recorder that computes cost perfectly and is never called by stream_turn
is the exact defect shape the 2026-07-27 review found three times over,
so these go through stream_turn rather than calling TurnUsage directly.
"""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import app.claude_client as claude_client_module
import app.tools  # noqa: F401  — registers the tools the label tests resolve
from app.claude_client import stream_turn
from app.config import (
    CACHE_READ_MULTIPLIER,
    CACHE_WRITE_MULTIPLIER,
    PRICE_INPUT_PER_MTOK,
    PRICE_OUTPUT_PER_MTOK,
)
from app.session import Session
from app.usage import (
    NO_TOOLS_LABEL,
    UNLABELED,
    SessionUsage,
    TurnUsage,
    phase_major,
)

from tests.test_claude_client_streaming import _fake_client_with_turns, fake_usage


class TestCostRespectsTheFourTokenClasses(unittest.TestCase):
    """The load-bearing arithmetic. Iris caches the spec and every tool
    schema on every call, so most input tokens on a real turn are cache
    reads at 0.1x. Billing them at the flat input rate would overstate
    input cost by roughly 10x on the cached portion, which is the number
    a pricing decision would be built on."""

    def test_cache_reads_cost_a_tenth_of_uncached_input(self) -> None:
        cached = TurnUsage()
        cached.record_call(fake_usage(input_tokens=0, cache_r=10_000, output_tokens=0))
        uncached = TurnUsage()
        uncached.record_call(fake_usage(input_tokens=10_000, output_tokens=0))

        self.assertAlmostEqual(
            cached.cost_usd, uncached.cost_usd * CACHE_READ_MULTIPLIER, places=10
        )

    def test_cache_writes_cost_a_premium_over_uncached_input(self) -> None:
        written = TurnUsage()
        written.record_call(fake_usage(input_tokens=0, cache_w=10_000, output_tokens=0))
        uncached = TurnUsage()
        uncached.record_call(fake_usage(input_tokens=10_000, output_tokens=0))

        self.assertAlmostEqual(
            written.cost_usd, uncached.cost_usd * CACHE_WRITE_MULTIPLIER, places=10
        )
        self.assertGreater(written.cost_usd, uncached.cost_usd)

    def test_full_cost_formula(self) -> None:
        turn = TurnUsage()
        turn.record_call(
            fake_usage(input_tokens=1_000, cache_w=30_000, cache_r=150_000, output_tokens=8_000)
        )
        expected = (
            (1_000 + 30_000 * CACHE_WRITE_MULTIPLIER + 150_000 * CACHE_READ_MULTIPLIER)
            * PRICE_INPUT_PER_MTOK
            + 8_000 * PRICE_OUTPUT_PER_MTOK
        ) / 1_000_000
        self.assertAlmostEqual(turn.cost_usd, expected, places=10)

    def test_a_cached_turn_is_cheaper_than_the_same_turn_uncached(self) -> None:
        """Stated as the property that actually motivates the caching,
        so a regression that flattens the rates fails here with an
        obvious meaning rather than an off-by-a-multiplier."""
        spec_and_schemas = 31_000
        cached = TurnUsage()
        cached.record_call(fake_usage(input_tokens=500, cache_r=spec_and_schemas, output_tokens=2_000))
        flat = TurnUsage()
        flat.record_call(fake_usage(input_tokens=500 + spec_and_schemas, output_tokens=2_000))
        self.assertLess(cached.cost_usd, flat.cost_usd)


class TestTokenAccumulation(unittest.TestCase):
    def test_counts_accumulate_across_api_calls(self) -> None:
        turn = TurnUsage()
        turn.record_call(fake_usage(input_tokens=100, cache_w=10, cache_r=1_000, output_tokens=50))
        turn.record_call(fake_usage(input_tokens=200, cache_w=0, cache_r=2_000, output_tokens=80))

        self.assertEqual(turn.api_calls, 2)
        self.assertEqual(turn.input_tokens, 300)
        self.assertEqual(turn.cache_creation_tokens, 10)
        self.assertEqual(turn.cache_read_tokens, 3_000)
        self.assertEqual(turn.output_tokens, 130)
        self.assertEqual(turn.total_tokens, 3_440)

    def test_missing_cache_fields_are_treated_as_zero(self) -> None:
        """Some responses omit the cache counters entirely. Accounting
        must never be the thing that breaks a turn that otherwise
        worked."""
        turn = TurnUsage()
        turn.record_call(SimpleNamespace(input_tokens=10, output_tokens=5))
        self.assertEqual(turn.cache_read_tokens, 0)
        self.assertEqual(turn.total_tokens, 15)

    def test_none_fields_are_treated_as_zero(self) -> None:
        turn = TurnUsage()
        turn.record_call(
            SimpleNamespace(
                input_tokens=10,
                output_tokens=5,
                cache_creation_input_tokens=None,
                cache_read_input_tokens=None,
            )
        )
        self.assertEqual(turn.total_tokens, 15)

    def test_a_missing_usage_object_still_counts_the_call(self) -> None:
        turn = TurnUsage()
        turn.record_call(None)
        self.assertEqual(turn.api_calls, 1)
        self.assertEqual(turn.total_tokens, 0)


class TestPhaseAttribution(unittest.TestCase):
    """Labeling reads the tool-list numbering, not session.phase. The
    2026-07-27 review established sessions never leave STARTING_POINT,
    so a phase-keyed measurement would file every turn in one bucket."""

    def test_major_parses_from_a_tool_id(self) -> None:
        self.assertEqual(phase_major("T-3.1"), 3)
        self.assertEqual(phase_major("T-11.2"), 11)

    def test_unparseable_ids_return_none_rather_than_raising(self) -> None:
        self.assertIsNone(phase_major("nonsense"))
        self.assertIsNone(phase_major(""))

    def test_a_turn_with_no_tools_is_conversation(self) -> None:
        turn = TurnUsage()
        turn.record_call(fake_usage())
        self.assertEqual(turn.label(), NO_TOOLS_LABEL)

    def test_modal_phase_wins(self) -> None:
        turn = TurnUsage()
        for _ in range(3):
            turn.record_tool("extract_facts", "T-2.4")
        turn.record_tool("check_em_dash", "T-3.1")
        self.assertEqual(turn.label(), "foundational_build")

    def test_ties_break_toward_the_earlier_phase(self) -> None:
        """A build that ends by running formatting checks is a build.
        Later-phase tools inside an earlier-phase turn are usually
        verification of the work, not the work."""
        turn = TurnUsage()
        turn.record_tool("extract_facts", "T-2.4")
        turn.record_tool("estimate_page_count", "T-4.11")
        self.assertEqual(turn.label(), "foundational_build")

    def test_harness_tools_never_decide_the_label(self) -> None:
        """T-9.x runs during turns of every kind and describes none of
        them. Left in the vote it would swamp the real signal."""
        turn = TurnUsage()
        for _ in range(5):
            turn.record_tool("harness_thing", "T-9.1")
        turn.record_tool("check_cover_letter_word_count", "T-7.2")
        self.assertEqual(turn.label(), "cover_letter")

    def test_only_harness_tools_is_unclassified_not_conversation(self) -> None:
        """The two are deliberately distinct: one means no tools ran,
        the other means the labeler could not read the ones that did.
        Collapsing them would hide a labeling bug as a usage pattern."""
        turn = TurnUsage()
        turn.record_tool("harness_thing", "T-9.1")
        self.assertEqual(turn.label(), UNLABELED)
        self.assertNotEqual(turn.label(), NO_TOOLS_LABEL)

    def test_an_unresolvable_tool_name_still_counts_as_tool_work(self) -> None:
        turn = TurnUsage()
        turn.record_tool("something_unregistered", None)
        self.assertEqual(turn.label(), UNLABELED)
        self.assertEqual(turn.tool_names, ["something_unregistered"])

    def test_phase_counts_report_the_raw_distribution(self) -> None:
        turn = TurnUsage()
        turn.record_tool("a", "T-1.1")
        turn.record_tool("b", "T-1.2")
        turn.record_tool("c", "T-7.1")
        turn.record_tool("d", "T-9.1")
        self.assertEqual(turn.phase_counts(), {"audit": 2, "cover_letter": 1})


class TestSessionAccumulation(unittest.TestCase):
    def test_turns_fold_into_session_totals(self) -> None:
        totals = SessionUsage()
        first = TurnUsage()
        first.record_call(fake_usage(input_tokens=100, cache_r=1_000, output_tokens=50))
        first.record_tool("check_em_dash", "T-3.1")
        second = TurnUsage()
        second.record_call(fake_usage(input_tokens=200, cache_r=2_000, output_tokens=80))
        second.record_tool("check_em_dash", "T-3.1")

        totals.record_turn(first)
        totals.record_turn(second)

        self.assertEqual(totals.turns, 2)
        self.assertEqual(totals.input_tokens, 300)
        self.assertEqual(totals.cache_read_tokens, 3_000)
        self.assertEqual(totals.by_label, {"slop_audit": 2})

    def test_a_turn_that_never_reached_the_api_is_not_counted(self) -> None:
        """These exist: an unconfigured key or a client disconnect can
        end a turn before anything is sent. Counting it would inflate
        the denominator of every per-turn average taken from this."""
        totals = SessionUsage()
        totals.record_turn(TurnUsage())
        self.assertEqual(totals.turns, 0)

    def test_session_cost_does_not_compound_rounding(self) -> None:
        """Computed from accumulated counts rather than by summing
        rounded per-turn figures."""
        totals = SessionUsage()
        for _ in range(100):
            turn = TurnUsage()
            turn.record_call(fake_usage(input_tokens=1, cache_r=1, output_tokens=1))
            totals.record_turn(turn)
        single = TurnUsage()
        single.record_call(fake_usage(input_tokens=100, cache_r=100, output_tokens=100))
        self.assertAlmostEqual(totals.cost_usd, single.cost_usd, places=10)


class TestUsageIsReachableThroughStreamTurn(unittest.TestCase):
    """Reachability, per the standard in README: enforcement and
    measurement are tested through the path a real turn takes, not by
    calling the recorder directly. A recorder nothing calls is the
    defect class this repo has paid for repeatedly."""

    def setUp(self) -> None:
        self.session = Session(session_id="s", user_id="u")

    _USE_DEFAULT = object()

    def _run(self, turns, session=_USE_DEFAULT):
        with patch.object(
            claude_client_module, "_client", return_value=_fake_client_with_turns(turns)
        ):
            return list(
                stream_turn(
                    spec_text="spec",
                    messages=[{"role": "user", "content": "hi"}],
                    session=self.session if session is self._USE_DEFAULT else session,
                    tool_ids=["T-3.1"],
                )
            )

    def test_a_completed_turn_lands_on_the_session(self) -> None:
        self._run([{
            "text_chunks": ["Done."],
            "content_blocks": [SimpleNamespace(type="text", text="Done.")],
            "stop_reason": "end_turn",
            "usage": fake_usage(input_tokens=500, cache_w=31_000, cache_r=0, output_tokens=200),
        }])
        self.assertEqual(self.session.usage.turns, 1)
        self.assertEqual(self.session.usage.input_tokens, 500)
        self.assertEqual(self.session.usage.cache_creation_tokens, 31_000)
        self.assertEqual(self.session.usage.output_tokens, 200)
        self.assertGreater(self.session.usage.cost_usd, 0)

    def test_every_api_call_in_a_tool_loop_is_counted(self) -> None:
        turns = [
            {
                "text_chunks": [],
                "content_blocks": [
                    SimpleNamespace(type="tool_use", id="t1", name="check_em_dash", input={"text": "clean"}),
                ],
                "stop_reason": "tool_use",
                "usage": fake_usage(input_tokens=100, cache_r=31_000, output_tokens=40),
            },
            {
                "text_chunks": ["Checked."],
                "content_blocks": [SimpleNamespace(type="text", text="Checked.")],
                "stop_reason": "end_turn",
                "usage": fake_usage(input_tokens=150, cache_r=31_000, output_tokens=60),
            },
        ]
        self._run(turns)
        # One turn, two API calls: the unit is the user action, not the
        # round trip.
        self.assertEqual(self.session.usage.turns, 1)
        self.assertEqual(self.session.usage.api_calls, 2)
        self.assertEqual(self.session.usage.input_tokens, 250)
        self.assertEqual(self.session.usage.cache_read_tokens, 62_000)
        self.assertEqual(self.session.usage.output_tokens, 100)

    def test_the_turn_is_labeled_from_the_tools_that_actually_ran(self) -> None:
        turns = [
            {
                "text_chunks": [],
                "content_blocks": [
                    SimpleNamespace(type="tool_use", id="t1", name="check_em_dash", input={"text": "clean"}),
                ],
                "stop_reason": "tool_use",
            },
            {
                "text_chunks": ["Checked."],
                "content_blocks": [SimpleNamespace(type="text", text="Checked.")],
                "stop_reason": "end_turn",
            },
        ]
        self._run(turns)
        # check_em_dash is T-3.1, so this turn is slop_audit work — and
        # it is labeled that way even though session.phase never left
        # STARTING_POINT, which is the whole reason labeling reads tools.
        self.assertEqual(self.session.usage.by_label, {"slop_audit": 1})
        self.assertEqual(self.session.phase, 0)

    def test_a_turn_that_fails_upstream_is_still_counted(self) -> None:
        """The first call was made and billed before the second failed.
        A turn that spent money and then errored is money spent."""
        import anthropic

        calls = {"n": 0}

        def _stream(**kwargs):
            if calls["n"] == 0:
                calls["n"] += 1
                from tests.test_claude_client_streaming import _FakeMessageStream

                return _FakeMessageStream(
                    [],
                    [SimpleNamespace(type="tool_use", id="t1", name="check_em_dash", input={"text": "x"})],
                    "tool_use",
                    fake_usage(input_tokens=100, cache_r=31_000, output_tokens=40),
                )
            raise anthropic.APIError("boom", request=MagicMock(), body=None)

        fake = MagicMock()
        fake.messages.stream.side_effect = _stream
        with patch.object(claude_client_module, "_client", return_value=fake):
            events = list(
                stream_turn(
                    spec_text="spec",
                    messages=[{"role": "user", "content": "hi"}],
                    session=self.session,
                    tool_ids=["T-3.1"],
                )
            )

        self.assertEqual(events[-1]["type"], "error")
        self.assertEqual(self.session.usage.turns, 1)
        self.assertEqual(self.session.usage.input_tokens, 100)

    def test_an_abandoned_stream_is_still_counted(self) -> None:
        """A client disconnect closes the generator part-way. The tokens
        were spent regardless, and a finally block is what makes that
        survive an exit path nobody wrote code for."""
        turns = [
            {
                "text_chunks": [],
                "content_blocks": [
                    SimpleNamespace(type="tool_use", id="t1", name="check_em_dash", input={"text": "clean"}),
                ],
                "stop_reason": "tool_use",
                "usage": fake_usage(input_tokens=100, cache_r=31_000, output_tokens=40),
            },
            {
                "text_chunks": ["Checked."],
                "content_blocks": [SimpleNamespace(type="text", text="Checked.")],
                "stop_reason": "end_turn",
            },
        ]
        with patch.object(
            claude_client_module, "_client", return_value=_fake_client_with_turns(turns)
        ):
            events = stream_turn(
                spec_text="spec",
                messages=[{"role": "user", "content": "hi"}],
                session=self.session,
                tool_ids=["T-3.1"],
            )
            # Consume up to the first tool_call. That is the first event
            # that can only appear after an API call has completed, so
            # reaching it means the first call was made and billed.
            # Stopping at the status event instead would prove nothing:
            # it is yielded before any call goes out.
            for event in events:
                if event["type"] == "tool_call":
                    break
            events.close()  # the client walks away mid-turn

        self.assertEqual(self.session.usage.turns, 1)
        self.assertEqual(self.session.usage.input_tokens, 100)

    def test_accounting_failure_never_breaks_the_turn(self) -> None:
        """It runs from a finally block, so an exception here would
        replace whatever was actually happening to the turn."""
        with patch.object(
            claude_client_module.TurnUsage, "as_log_fields", side_effect=RuntimeError("boom")
        ):
            events = self._run([{
                "text_chunks": ["Done."],
                "content_blocks": [SimpleNamespace(type="text", text="Done.")],
                "stop_reason": "end_turn",
            }])
        self.assertEqual(events[-1]["type"], "done")
        self.assertEqual(events[-1]["text"], "Done.")

    def test_a_turn_with_no_session_still_completes(self) -> None:
        """There is nowhere to accumulate totals, but the log line is
        still written and the turn must not care."""
        events = self._run(
            [{
                "text_chunks": ["Done."],
                "content_blocks": [SimpleNamespace(type="text", text="Done.")],
                "stop_reason": "end_turn",
            }],
            session=None,
        )
        self.assertEqual(events[-1]["type"], "done")


if __name__ == "__main__":
    unittest.main()
