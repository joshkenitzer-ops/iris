"""
Pins the upstream HTTP behavior of the Anthropic client (2026-07-27).

Worth recording why these exist, because the review that prompted them
was partly wrong: it claimed there was "no retry on upstream 429 or
5xx". The SDK already retried 408/409/429/5xx with exponential backoff,
twice, and already applied a 600s read / 5s connect timeout. Nothing was
unprotected.

What was true is that all of it was inherited rather than chosen, and an
inherited default is one a dependency upgrade can change silently. These
tests fail if that happens, which is the actual point.
"""

import os
import unittest
from unittest.mock import patch

from app.config import MODEL_CONNECT_TIMEOUT_SECONDS, MODEL_MAX_RETRIES, MODEL_READ_TIMEOUT_SECONDS


class TestClientConfiguration(unittest.TestCase):
    def setUp(self) -> None:
        from app.claude_client import reset_client_for_testing

        reset_client_for_testing()
        self._env = patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
        self._env.start()

    def tearDown(self) -> None:
        from app.claude_client import reset_client_for_testing

        self._env.stop()
        reset_client_for_testing()

    def test_retries_are_set_explicitly_not_inherited(self) -> None:
        from app.claude_client import _client

        self.assertEqual(_client().max_retries, MODEL_MAX_RETRIES)

    def test_retries_exceed_the_sdk_default(self) -> None:
        """The asymmetry justifies it: a retry costs a second of backoff,
        a failure surfacing mid-Master-Build costs the user three minutes
        of work they then repeat."""
        from anthropic._constants import DEFAULT_MAX_RETRIES

        self.assertGreater(MODEL_MAX_RETRIES, DEFAULT_MAX_RETRIES)

    def test_read_timeout_bounds_a_hung_request(self) -> None:
        """Read timeout is time between chunks, not total duration, since
        every call streams. 600s let a genuinely stuck request hold a
        per-session lock for ten minutes."""
        from app.claude_client import _client

        timeout = _client().timeout
        self.assertEqual(timeout.read, MODEL_READ_TIMEOUT_SECONDS)
        self.assertLess(timeout.read, 600)

    def test_connect_timeout_is_short(self) -> None:
        from app.claude_client import _client

        self.assertEqual(_client().timeout.connect, MODEL_CONNECT_TIMEOUT_SECONDS)

    def test_client_is_reused_across_calls(self) -> None:
        """Constructing per turn discarded the httpx connection pool and
        paid a fresh TLS handshake every turn."""
        from app.claude_client import _client

        self.assertIs(_client(), _client())

    def test_missing_api_key_still_raises_before_any_client_is_built(self) -> None:
        from app.claude_client import _client, reset_client_for_testing

        reset_client_for_testing()
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                _client()


if __name__ == "__main__":
    unittest.main()
