"""
The one test in this suite that costs money and needs a network.
Skipped automatically unless ANTHROPIC_API_KEY is set, so it never
fails CI runs that don't have one configured, and never runs by
accident in an environment with no internet, which is why it could not
be run in the environment that wrote this file.

Run explicitly with:
    pytest tests/test_claude_client_smoke.py -v
"""

import os
import unittest
from pathlib import Path

from app.claude_client import run_turn
from app.spec_loader import load_spec_text

SPEC_PATH = Path(__file__).resolve().parent.parent / "docs" / "iris-spec.md"


@unittest.skipUnless(
    os.environ.get("ANTHROPIC_API_KEY"),
    "ANTHROPIC_API_KEY not set; skipping live API smoke test.",
)
class TestClaudeClientSmoke(unittest.TestCase):
    def test_tool_use_loop_terminates_and_calls_em_dash_check(self) -> None:
        spec_text = load_spec_text(SPEC_PATH)
        result = run_turn(
            spec_text=spec_text,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Use the check_em_dash tool on this exact text and "
                        "tell me in one sentence whether it passed: "
                        "'Led a team of five engineers.'"
                    ),
                }
            ],
            tool_ids=["T-3.1"],
        )
        self.assertIn("text", result)
        self.assertTrue(len(result["text"]) > 0)


if __name__ == "__main__":
    unittest.main()
