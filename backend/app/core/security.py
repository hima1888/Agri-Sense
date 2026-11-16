"""Verification of Supabase Auth access tokens (JWTs).

Supabase signs access tokens either with an asymmetric key (ES256/RS256; the
current default, public keys published at <SUPABASE_URL>/auth/v1/.well-known/jwks.json)
or, on older projects, with a shared HS256 secret. Both are supported; only the
algorithms that are actually configured are accepted, so a token can never pick a
weaker algorithm for itself (e.g. `none`, or HS256 signed with a public key).
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import httpx
import jwt
from jwt import PyJWK

logger = logging.getLogger("agri_sense.auth")

ASYMMETRIC_ALGS = frozenset({"ES256", "RS256"})
JwksFetcher = Callable[[], dict[str, Any]]


class TokenError(Exception):
    """The token is missing, malformed, expired or not trusted. Message is safe to show."""


@dataclass(frozen=True)
class AuthClaims:
    user_id: UUID
    email: str | None
    session_id: str | None
    raw: dict[str, Any]


def http_jwks_fetcher(jwks_url: str) -> JwksFetcher:
    def fetch() -> dict[str, Any]:
        res = httpx.get(jwks_url, timeout=5.0)
        res.raise_for_status()
        data: dict[str, Any] = res.json()
        return data

    return fetch


class TokenVerifier:
    def __init__(
        self,
        *,
        issuer: str | None,
        audience: str = "authenticated",
        hs256_secret: str | None = None,
        jwks_fetcher: JwksFetcher | None = None,
        jwks_ttl_seconds: float = 600,
        leeway_seconds: int = 30,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not hs256_secret and jwks_fetcher is None:
            raise ValueError("Configure SUPABASE_URL (JWKS) and/or SUPABASE_JWT_SECRET to verify tokens.")
        self.issuer = issuer
        self.audience = audience
        self.hs256_secret = hs256_secret or None
        self.jwks_fetcher = jwks_fetcher
        self.jwks_ttl = jwks_ttl_seconds
        self.leeway = leeway_seconds
        self._clock = clock
        self._keys: dict[str, PyJWK] = {}
        self._fetched_at = float("-inf")
        self._lock = threading.Lock()

    # -- JWKS cache -------------------------------------------------------
    def _refresh(self) -> None:
        assert self.jwks_fetcher is not None
        jwks = self.jwks_fetcher()
        keys: dict[str, PyJWK] = {}
        for jwk in jwks.get("keys", []):
            if jwk.get("kid") and jwk.get("alg") in ASYMMETRIC_ALGS:
                keys[jwk["kid"]] = PyJWK(jwk)
        self._keys = keys
        self._fetched_at = self._clock()

    def _key_for(self, kid: str | None) -> PyJWK:
        if self.jwks_fetcher is None:
            raise TokenError("Asymmetric tokens are not accepted by this server.")
        if not kid:
            raise TokenError("Token header has no key id.")
        with self._lock:
            stale = self._clock() - self._fetched_at > self.jwks_ttl
            # Unknown kid may mean key rotation: refetch, but at most once per 30 s.
            unknown_kid_retry = kid not in self._keys and self._clock() - self._fetched_at > 30
            if stale or unknown_kid_retry:
                try:
                    self._refresh()
                except (httpx.HTTPError, ValueError) as exc:
                    logger.warning("JWKS fetch failed: %s", type(exc).__name__)
                    if not self._keys:
                        raise TokenError("Unable to load token signing keys.") from exc
            key = self._keys.get(kid)
        if key is None:
            raise TokenError("Token signed with an unknown key.")
        return key

    # -- verification -----------------------------------------------------
    def verify(self, token: str) -> AuthClaims:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise TokenError("Malformed token.") from exc

        alg = header.get("alg")
        key: Any
        if alg in ASYMMETRIC_ALGS:
            jwk = self._key_for(header.get("kid"))
            if jwk.algorithm_name != alg:
                raise TokenError("Token algorithm does not match its key.")
            key = jwk.key
        elif alg == "HS256" and self.hs256_secret:
            key = self.hs256_secret
        else:
            raise TokenError("Token algorithm not accepted.")

        try:
            claims: dict[str, Any] = jwt.decode(
                token,
                key=key,
                algorithms=[alg],
                audience=self.audience,
                issuer=self.issuer,
                leeway=self.leeway,
                options={"require": ["exp", "sub", "aud"], "verify_iss": self.issuer is not None},
            )
        except jwt.ExpiredSignatureError as exc:
            raise TokenError("Token has expired.") from exc
        except jwt.PyJWTError as exc:
            raise TokenError("Token is not valid.") from exc

        if claims.get("role") != "authenticated" or claims.get("is_anonymous") is True:
            raise TokenError("Only signed-in users may call this API.")
        try:
            user_id = UUID(str(claims["sub"]))
        except ValueError as exc:
            raise TokenError("Token subject is not a user id.") from exc
        email = claims.get("email")
        return AuthClaims(
            user_id=user_id,
            email=str(email).lower() if email else None,
            session_id=claims.get("session_id"),
            raw=claims,
        )
