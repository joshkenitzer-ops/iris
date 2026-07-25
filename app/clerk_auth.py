"""
T-9.10: authentication. Real verification of a Clerk-issued session
token, replacing the X-User-Id header stub that main.py used to trust
outright.

Design intent, spelled out because it's the whole point of this file:
the client never gets to assert who they are. A request carries an
opaque JWT that Clerk signed; this module verifies that signature
against Clerk's own published public keys, checks the token hasn't
expired and was issued by the expected Clerk instance, and only then
extracts the user id that Clerk itself put in the token (the `sub`
claim). Nothing here trusts a header, a path parameter, or a query
parameter for identity. If verification fails for any reason, the
caller gets a single generic "invalid or expired session token". The
specific cause (bad signature, wrong issuer, expired, malformed) is
for server logs, never for the client, since a specific error message
here would help an attacker iterate toward a forged token.

Fails closed: if CLERK_ISSUER isn't configured, get_verifier() raises
rather than falling back to any permissive default. There is no mode
in which this module grants access without a successfully verified
token.

Setup (do this against your actual Clerk dashboard, not this
comment): CLERK_ISSUER is your Clerk Frontend API URL, shown on the
Clerk dashboard's API Keys page, typically
"https://<your-instance>.clerk.accounts.dev" in development or your
custom domain in production. Clerk publishes its JWKS at
"<issuer>/.well-known/jwks.json"; this module builds that URL from
CLERK_ISSUER rather than needing it spelled out separately. Confirm
both URLs against your own dashboard before deploying, since Clerk's
exact paths can change between plan tiers.

Optional CLERK_AUTHORIZED_PARTIES (comma-separated origins) checks the
token's `azp` claim, the frontend origin Clerk issued the token for,
rejecting a token that's valid but was minted for a different
frontend than the one talking to this API. Recommended once you know
your frontend's real origin; omitted, that specific check is skipped
without weakening signature/expiry/issuer verification, which always
runs.
"""

from __future__ import annotations

import os
import threading
from typing import Callable, List, Optional

import jwt


class ClerkAuthError(Exception):
    """Any failure verifying a Clerk session token: bad signature,
    expired, wrong issuer, wrong authorized party, malformed token, or
    a JWKS fetch failure. Deliberately one exception type for all of
    these; callers must not branch on the specific cause when deciding
    what to tell the client (see module docstring)."""


class ClerkVerifier:
    """Verifies Clerk session tokens against one Clerk instance's
    published keys. jwk_client_factory exists so tests can inject a
    fake JWKS source instead of hitting Clerk's real servers; the
    default builds a real jwt.PyJWKClient, which handles fetching and
    caching the JWKS and matching a token's `kid` to the right key,
    including key rotation, without this module reimplementing any of
    that."""

    def __init__(
        self,
        issuer: str,
        authorized_parties: Optional[List[str]] = None,
        jwk_client_factory: Optional[Callable[[str], object]] = None,
    ) -> None:
        if not issuer or not issuer.strip():
            raise ValueError("issuer is required and cannot be blank.")
        self._issuer = issuer.rstrip("/")
        self._authorized_parties = set(authorized_parties or [])
        factory = jwk_client_factory or (lambda jwks_url: jwt.PyJWKClient(jwks_url))
        self._jwk_client = factory(f"{self._issuer}/.well-known/jwks.json")

    def verify(self, token: str) -> str:
        """Returns the verified Clerk user id (the `sub` claim) or
        raises ClerkAuthError. Signature, expiry, and issuer are
        always checked; authorized-party is checked only if
        CLERK_AUTHORIZED_PARTIES was configured."""
        try:
            signing_key = self._jwk_client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                issuer=self._issuer,
                options={"require": ["exp", "iat", "sub"]},
            )
        except jwt.PyJWTError as exc:
            raise ClerkAuthError(f"Token verification failed: {exc}") from exc
        except Exception as exc:  # noqa: BLE001 - JWKS fetch/network failures land here too
            raise ClerkAuthError(f"Could not verify token: {exc}") from exc

        if self._authorized_parties:
            azp = claims.get("azp")
            if azp not in self._authorized_parties:
                raise ClerkAuthError(f"Token's authorized party '{azp}' is not in CLERK_AUTHORIZED_PARTIES.")

        sub = claims.get("sub")
        if not sub or not str(sub).strip():
            raise ClerkAuthError("Token has no usable 'sub' claim.")
        return str(sub)


_verifier: Optional[ClerkVerifier] = None
_verifier_lock = threading.Lock()


def get_verifier() -> ClerkVerifier:
    """Lazily builds the process-wide verifier from environment
    variables, once. Raises RuntimeError, not a permissive default, if
    CLERK_ISSUER is unset - a misconfigured server must refuse to
    verify anyone rather than silently accepting everyone."""
    global _verifier
    if _verifier is not None:
        return _verifier
    with _verifier_lock:
        if _verifier is None:
            issuer = os.environ.get("CLERK_ISSUER")
            if not issuer or not issuer.strip():
                raise RuntimeError(
                    "CLERK_ISSUER is not set. Auth must fail closed rather "
                    "than fall back to trusting an unverified header; set "
                    "CLERK_ISSUER (your Clerk Frontend API URL) in the "
                    "environment before serving requests."
                )
            raw_parties = os.environ.get("CLERK_AUTHORIZED_PARTIES", "")
            authorized_parties = [p.strip() for p in raw_parties.split(",") if p.strip()]
            _verifier = ClerkVerifier(issuer, authorized_parties=authorized_parties or None)
    return _verifier


def reset_verifier_for_testing() -> None:
    """Test-only escape hatch: clears the cached singleton so a test
    can point CLERK_ISSUER at a fresh fake issuer and get a fresh
    verifier, rather than reusing whatever the first test configured."""
    global _verifier
    with _verifier_lock:
        _verifier = None
