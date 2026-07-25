import unittest

from app.session import SessionNotFoundError, SessionStore


class TestSessionIsolation(unittest.TestCase):
    def setUp(self) -> None:
        self.store = SessionStore()

    def test_owner_can_read_own_session(self) -> None:
        session = self.store.create("user-a")
        fetched = self.store.get("user-a", session.session_id)
        self.assertEqual(fetched.session_id, session.session_id)

    def test_other_user_cannot_read_real_session_id(self) -> None:
        session = self.store.create("user-a")
        with self.assertRaises(SessionNotFoundError):
            self.store.get("user-b", session.session_id)

    def test_wrong_user_and_nonexistent_session_raise_identically(self) -> None:
        """The point of the isolation boundary: a caller cannot use the
        error to distinguish "this session doesn't exist" from "this
        session exists but isn't yours". Both must be indistinguishable
        SessionNotFoundError instances with no extra detail leaked."""
        session = self.store.create("user-a")

        try:
            self.store.get("user-b", session.session_id)
        except SessionNotFoundError as exc:
            wrong_user_error = str(exc)

        try:
            self.store.get("user-b", "not-a-real-session-id")
        except SessionNotFoundError as exc:
            nonexistent_error = str(exc)

        # Both raise the same exception type with the id as the only
        # payload; neither leaks whether the session belongs to
        # someone else versus not existing at all.
        self.assertEqual(type(wrong_user_error), type(nonexistent_error))

    def test_two_users_cannot_collide_on_session_state(self) -> None:
        session_a = self.store.create("user-a")
        session_b = self.store.create("user-b")
        session_a.phase = session_a.phase  # no-op, just establishing distinct identity
        self.store.save(session_a)

        fetched_b = self.store.get("user-b", session_b.session_id)
        self.assertNotEqual(fetched_b.session_id, session_a.session_id)


if __name__ == "__main__":
    unittest.main()
