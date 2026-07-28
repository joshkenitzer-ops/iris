"""Coverage for resuming a session after a page reload.

Reported live 2026-07-28: refreshing the browser lost the session and
the user restarted from scratch. Two separate causes, both here.

GET /sessions/{id} confirmed a session existed but returned nothing
that could be put back on screen, so even a correct client had no
transcript to render. And static/app.js never called the function
written to resume a saved session at all: it was defined, referenced
once from a comment, and dead. The only path to a session was the
"Start a session" button, which mints a new one unconditionally and
overwrites the saved id, so a reload orphaned a live session (its
transcript, extracted facts, and rendered files all still held
server-side) and handed the user an empty one.

That is the same defect shape as the delivery gates, the download
route, and the page-length checks before it: correct logic nothing ever
called. The route half is tested here. The wiring half is JavaScript
and cannot be exercised by this suite, which is precisely why the route
contract it depends on is pinned this thoroughly.
"""

import unittest
import uuid
from unittest.mock import patch

from tests.test_main_integration import _AuthOverriddenTestCase


class TestGetSessionReturnsWhatARefreshNeeds(_AuthOverriddenTestCase):
    def test_a_fresh_session_reports_an_empty_transcript(self) -> None:
        """Present and empty, not absent. A client should never have to
        distinguish "no messages" from "this server predates the
        field"."""
        session_id = self._create_session()
        body = self.client.get(f"/sessions/{session_id}").json()
        self.assertEqual(body["messages"], [])
        self.assertEqual(body["files"], [])

    def test_the_conversation_comes_back_in_order(self) -> None:
        session_id = self._create_session()
        session = self.module.store.get(self.user_id, session_id)
        session.append_messages([
            {"role": "user", "content": "Here is my resume."},
            {"role": "assistant", "content": "Running the audit now."},
            {"role": "user", "content": "Go ahead and build it."},
        ])

        messages = self.client.get(f"/sessions/{session_id}").json()["messages"]
        self.assertEqual(
            [(m["role"], m["text"]) for m in messages],
            [
                ("user", "Here is my resume."),
                ("assistant", "Running the audit now."),
                ("user", "Go ahead and build it."),
            ],
        )

    def test_tool_traffic_is_not_replayed_as_conversation(self) -> None:
        """session.messages is the model's context and carries tool_use
        and tool_result blocks that were never on screen. Returning them
        would put raw harness plumbing in front of the user."""
        session_id = self._create_session()
        session = self.module.store.get(self.user_id, session_id)
        session.append_messages([
            {"role": "user", "content": "Check this."},
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Let me run the checks."},
                    {"type": "tool_use", "id": "t1", "name": "check_em_dash", "input": {}},
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "t1", "content": "{}"},
                ],
            },
            {"role": "assistant", "content": "All clean."},
        ])

        messages = self.client.get(f"/sessions/{session_id}").json()["messages"]
        self.assertEqual(
            [(m["role"], m["text"]) for m in messages],
            [
                ("user", "Check this."),
                ("assistant", "Let me run the checks."),
                ("assistant", "All clean."),
            ],
        )

    def test_a_turn_that_was_only_tool_calls_is_dropped_entirely(self) -> None:
        """Filtering a message down to nothing must remove it, not
        leave an empty bubble on screen."""
        session_id = self._create_session()
        session = self.module.store.get(self.user_id, session_id)
        session.append_messages([
            {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": "t1", "name": "check_em_dash", "input": {}}],
            },
        ])
        self.assertEqual(self.client.get(f"/sessions/{session_id}").json()["messages"], [])

    def test_rendered_files_come_back_so_downloads_survive_a_reload(self) -> None:
        """A resume the user already generated is the most expensive
        thing in the session. Losing the button to it on refresh loses
        the artifact as far as the user is concerned."""
        session_id = self._create_session()
        session = self.module.store.get(self.user_id, session_id)
        rendered = session.add_rendered_file(
            "Kenitzer_Joshua_Foundational_Resume.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "ZmFrZQ==",
        )

        files = self.client.get(f"/sessions/{session_id}").json()["files"]
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0]["file_id"], rendered.id)
        self.assertEqual(files[0]["filename"], "Kenitzer_Joshua_Foundational_Resume.docx")

    def test_the_file_id_returned_is_the_one_the_download_route_accepts(self) -> None:
        """Pins the pair together. The download button was already
        broken once by being handed a filename where the route expects
        a file_id (2026-07-27); restoring buttons from this payload is
        a second chance to make the same mistake."""
        session_id = self._create_session()
        session = self.module.store.get(self.user_id, session_id)
        session.add_rendered_file("resume.docx", "application/octet-stream", "ZmFrZQ==")

        file_id = self.client.get(f"/sessions/{session_id}").json()["files"][0]["file_id"]
        download = self.client.get(f"/sessions/{session_id}/files/{file_id}")
        self.assertEqual(download.status_code, 200, download.text)

    def test_another_users_session_is_still_not_readable(self) -> None:
        """The route now returns the full conversation, which raises
        the stakes on the isolation boundary it sits behind (T-9.12).
        Same 404 as a session that does not exist."""
        session_id = self._create_session()
        session = self.module.store.get(self.user_id, session_id)
        session.append_messages([{"role": "user", "content": "private"}])

        other = f"user_test_{uuid.uuid4().hex[:12]}"
        self.module.app.dependency_overrides[self.module.get_current_user_id] = lambda: other
        response = self.client.get(f"/sessions/{session_id}")
        self.assertEqual(response.status_code, 404)
        self.assertNotIn("private", response.text)


class TestSessionAge(_AuthOverriddenTestCase):
    """A resumed session says how old it is, so a day-old conversation
    does not look identical to one from two minutes ago."""

    def test_a_session_with_no_turns_reports_no_age(self) -> None:
        session_id = self._create_session()
        body = self.client.get(f"/sessions/{session_id}").json()
        self.assertIsNone(body["last_active_seconds_ago"])

    def test_age_is_measured_from_the_last_turn_not_the_last_read(self) -> None:
        """The trap this field exists to avoid. SessionStore.get()
        sets last_accessed on every lookup, including the boot-time
        existence check that precedes this very request, so an age
        derived from it would always report zero no matter how old the
        conversation actually was."""
        import time as time_module

        session_id = self._create_session()
        session = self.module.store.get(self.user_id, session_id)
        session.append_messages([{"role": "user", "content": "hello"}])
        # Backdate the turn by an hour, then read through the route,
        # which touches last_accessed on the way in.
        session.last_turn_at = time_module.monotonic() - 3600

        age = self.client.get(f"/sessions/{session_id}").json()["last_active_seconds_ago"]
        self.assertGreater(age, 3500)

    def test_a_fresh_turn_reports_a_near_zero_age(self) -> None:
        session_id = self._create_session()
        session = self.module.store.get(self.user_id, session_id)
        session.append_messages([{"role": "user", "content": "hello"}])
        age = self.client.get(f"/sessions/{session_id}").json()["last_active_seconds_ago"]
        self.assertLess(age, 60)

    def test_an_empty_append_does_not_count_as_activity(self) -> None:
        """Otherwise a no-op call would keep resetting the clock and
        an idle session would claim to be freshly active."""
        from app.session import Session

        session = Session(session_id="s", user_id="u")
        session.append_messages([])
        self.assertIsNone(session.last_turn_at)


class TestTranscriptProjection(unittest.TestCase):
    """Direct coverage of the projection's edge cases, which are
    awkward to reach through the route."""

    def _project(self, messages):
        import app.main as main_module
        from app.session import Session

        session = Session(session_id="s", user_id="u")
        session.messages = list(messages)
        return main_module._transcript_for_display(session)

    def test_non_conversational_roles_are_skipped(self) -> None:
        self.assertEqual(self._project([{"role": "system", "content": "internal"}]), [])

    def test_whitespace_only_text_is_dropped(self) -> None:
        self.assertEqual(self._project([{"role": "assistant", "content": "   \n  "}]), [])

    def test_multiple_text_blocks_in_one_turn_are_joined(self) -> None:
        result = self._project([
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "First part. "},
                    {"type": "text", "text": "Second part."},
                ],
            }
        ])
        self.assertEqual(result, [{"role": "assistant", "text": "First part. Second part."}])

    def test_unexpected_content_shapes_do_not_raise(self) -> None:
        """A reload path must not be able to 500 on a transcript shape
        it did not anticipate. Skipping a message the user cannot see
        anyway beats failing the whole restore."""
        self.assertEqual(self._project([{"role": "user", "content": None}]), [])
        self.assertEqual(self._project([{"role": "user"}]), [])
        self.assertEqual(self._project([{"role": "user", "content": [None, 7]}]), [])


if __name__ == "__main__":
    unittest.main()
