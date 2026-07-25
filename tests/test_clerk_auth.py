"""
Tests app.clerk_auth against a throwaway RSA keypair generated in this
process, standing in for Clerk's real signing key. No network call,
no real Clerk tenant needed: jwk_client_factory is the seam that lets
these tests supply a fake JWKS source while exercising exactly the
same jwt.decode() verification path production uses against a real
one. This mirrors the pattern used elsewhere for the one dependency
that genuinely needs a live network call (ANTHROPIC_API_KEY / the
Claude smoke test): verify the logic fully offline, reserve the live
call for a separate manual/smoke check against your actual Clerk
instance.
"""

import time
import unittest

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.clerk_auth import ClerkAuthError, ClerkVerifier

ISSUER = "https://test-app.clerk.accounts.dev"
KID = "test-key-1"


def _pem(private_key) -> bytes:
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


class _FakeSigningKey:
    def __init__(self, key):
        self.key = key


class _FakeJWKClient:
    """Stands in for jwt.PyJWKClient: same interface, no network."""

    def __init__(self, public_key):
        self._public_key = public_key

    def get_signing_key_from_jwt(self, token):
        return _FakeSigningKey(self._public_key)


class TestClerkVerifier(unittest.TestCase):
    def setUp(self) -> None:
        self.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.public_key = self.private_key.public_key()
        self.private_pem = _pem(self.private_key)
        self.verifier = ClerkVerifier(
            ISSUER,
            jwk_client_factory=lambda jwks_url: _FakeJWKClient(self.public_key),
        )

    def _make_token(self, overrides=None, kid=KID, key_pem=None):
        now = int(time.time())
        claims = {"sub": "user_abc123", "iss": ISSUER, "iat": now, "exp": now + 300}
        if overrides:
            claims.update(overrides)
        return jwt.encode(claims, key_pem or self.private_pem, algorithm="RS256", headers={"kid": kid})

    def test_valid_token_returns_the_sub_claim(self) -> None:
        sub = self.verifier.verify(self._make_token())
        self.assertEqual(sub, "user_abc123")

    def test_expired_token_is_rejected(self) -> None:
        token = self._make_token({"exp": int(time.time()) - 10})
        with self.assertRaises(ClerkAuthError):
            self.verifier.verify(token)

    def test_wrong_issuer_is_rejected(self) -> None:
        token = self._make_token({"iss": "https://not-your-clerk-instance.example.com"})
        with self.assertRaises(ClerkAuthError):
            self.verifier.verify(token)

    def test_forged_signature_is_rejected(self) -> None:
        """The critical case: a token claiming to be valid but signed
        with a key that isn't the one this verifier trusts must never
        be accepted, regardless of what its claims say."""
        other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        forged = self._make_token(key_pem=_pem(other_key))
        with self.assertRaises(ClerkAuthError):
            self.verifier.verify(forged)

    def test_missing_sub_claim_is_rejected(self) -> None:
        now = int(time.time())
        claims = {"iss": ISSUER, "iat": now, "exp": now + 300}  # no 'sub'
        token = jwt.encode(claims, self.private_pem, algorithm="RS256", headers={"kid": KID})
        with self.assertRaises(ClerkAuthError):
            self.verifier.verify(token)

    def test_blank_sub_claim_is_rejected(self) -> None:
        token = self._make_token({"sub": "   "})
        with self.assertRaises(ClerkAuthError):
            self.verifier.verify(token)

    def test_alg_none_attack_is_rejected(self) -> None:
        """A classic JWT attack: a token that declares alg=none and
        carries no signature at all. jwt.decode with
        algorithms=["RS256"] must refuse this outright."""
        now = int(time.time())
        claims = {"sub": "user_abc123", "iss": ISSUER, "iat": now, "exp": now + 300}
        unsigned = jwt.encode(claims, None, algorithm="none")
        with self.assertRaises(ClerkAuthError):
            self.verifier.verify(unsigned)

    def test_malformed_token_is_rejected_not_raised_as_something_else(self) -> None:
        with self.assertRaises(ClerkAuthError):
            self.verifier.verify("not-a-real-jwt-at-all")

    def test_empty_issuer_is_rejected_at_construction(self) -> None:
        with self.assertRaises(ValueError):
            ClerkVerifier("", jwk_client_factory=lambda url: _FakeJWKClient(self.public_key))


class TestClerkVerifierAuthorizedParties(unittest.TestCase):
    def setUp(self) -> None:
        self.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.public_key = self.private_key.public_key()
        self.private_pem = _pem(self.private_key)

    def _make_token(self, overrides=None):
        now = int(time.time())
        claims = {"sub": "user_abc123", "iss": ISSUER, "iat": now, "exp": now + 300}
        if overrides:
            claims.update(overrides)
        return jwt.encode(claims, self.private_pem, algorithm="RS256", headers={"kid": KID})

    def test_no_authorized_parties_configured_skips_the_check(self) -> None:
        verifier = ClerkVerifier(ISSUER, jwk_client_factory=lambda url: _FakeJWKClient(self.public_key))
        sub = verifier.verify(self._make_token({"azp": "https://anything.example.com"}))
        self.assertEqual(sub, "user_abc123")

    def test_matching_authorized_party_passes(self) -> None:
        verifier = ClerkVerifier(
            ISSUER,
            authorized_parties=["https://myapp.example.com"],
            jwk_client_factory=lambda url: _FakeJWKClient(self.public_key),
        )
        sub = verifier.verify(self._make_token({"azp": "https://myapp.example.com"}))
        self.assertEqual(sub, "user_abc123")

    def test_mismatched_authorized_party_is_rejected(self) -> None:
        verifier = ClerkVerifier(
            ISSUER,
            authorized_parties=["https://myapp.example.com"],
            jwk_client_factory=lambda url: _FakeJWKClient(self.public_key),
        )
        with self.assertRaises(ClerkAuthError):
            verifier.verify(self._make_token({"azp": "https://a-different-app.example.com"}))

    def test_missing_azp_when_required_is_rejected(self) -> None:
        verifier = ClerkVerifier(
            ISSUER,
            authorized_parties=["https://myapp.example.com"],
            jwk_client_factory=lambda url: _FakeJWKClient(self.public_key),
        )
        with self.assertRaises(ClerkAuthError):
            verifier.verify(self._make_token())  # no azp claim at all


class TestGetVerifierFailsClosed(unittest.TestCase):
    def setUp(self) -> None:
        import app.clerk_auth as clerk_auth_module

        self._module = clerk_auth_module
        self._original_issuer = None

    def test_missing_clerk_issuer_raises_not_falls_back(self) -> None:
        import os

        from app.clerk_auth import get_verifier, reset_verifier_for_testing

        original = os.environ.pop("CLERK_ISSUER", None)
        reset_verifier_for_testing()
        try:
            with self.assertRaises(RuntimeError):
                get_verifier()
        finally:
            if original is not None:
                os.environ["CLERK_ISSUER"] = original
            reset_verifier_for_testing()


if __name__ == "__main__":
    unittest.main()
