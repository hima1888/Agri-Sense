"""Token verification and request authentication."""

import uuid
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from app.core.security import TokenError
from tests.api.helpers import V1, err, ok
from tests.conftest import ClientFor, make_token, make_verifier

UID = uuid.UUID("11111111-2222-3333-4444-555555555555")


def test_valid_es256_token_is_accepted() -> None:
    claims = make_verifier().verify(make_token(UID, "Grower@Example.com"))
    assert claims.user_id == UID
    assert claims.email == "grower@example.com"  # normalised


@pytest.mark.parametrize(
    ("token_kwargs", "message"),
    [
        ({"expires_in": -120}, "expired"),
        ({"aud": "anon"}, "not valid"),
        ({"iss": "https://evil.example.com/auth/v1"}, "not valid"),
        ({"role": "anon"}, "signed-in users"),
        ({"role": "service_role"}, "signed-in users"),
        ({"is_anonymous": True}, "signed-in users"),
        ({"kid": "unknown-key"}, "unknown key"),
        ({"key": ec.generate_private_key(ec.SECP256R1())}, "not valid"),  # forged signature
        ({"sub": "not-a-uuid"}, "not a user id"),
    ],
)
def test_untrusted_tokens_are_rejected(token_kwargs: dict[str, Any], message: str) -> None:
    sub = token_kwargs.pop("sub", UID)
    with pytest.raises(TokenError, match=message):
        make_verifier().verify(make_token(sub, **token_kwargs))


def test_algorithm_confusion_is_rejected() -> None:
    verifier = make_verifier()
    hs = jwt.encode(
        {"sub": str(UID), "aud": "authenticated", "exp": 9_999_999_999}, "x" * 32, algorithm="HS256"
    )
    with pytest.raises(TokenError, match="algorithm not accepted"):
        verifier.verify(hs)  # HS256 is off unless a secret is configured
    none = jwt.encode({"sub": str(UID)}, key="", algorithm="none")
    with pytest.raises(TokenError):
        verifier.verify(none)
    with pytest.raises(TokenError, match="Malformed"):
        verifier.verify("not.a.jwt")


def test_legacy_hs256_secret_mode() -> None:
    secret = "a-legacy-project-jwt-secret-of-32-chars!"
    verifier = make_verifier(hs256_secret=secret, jwks_fetcher=None)
    token = make_token(UID, key=secret, alg="HS256")
    assert verifier.verify(token).user_id == UID
    with pytest.raises(TokenError):
        verifier.verify(make_token(UID, key="wrong-secret-wrong-secret-wrong-secret", alg="HS256"))


def test_jwks_is_cached_and_refetched_for_a_rotated_key() -> None:
    calls = {"n": 0}
    keys: list[dict[str, Any]] = []
    now = {"t": 1000.0}

    def fetch() -> dict[str, Any]:
        calls["n"] += 1
        return {"keys": keys}

    from tests.conftest import _PUBLIC_JWK

    keys.append(_PUBLIC_JWK)
    verifier = make_verifier(jwks_fetcher=fetch, clock=lambda: now["t"])
    verifier.verify(make_token(UID))
    verifier.verify(make_token(UID))
    assert calls["n"] == 1  # cached
    # A token with an unknown kid triggers at most one refetch per 30 s.
    with pytest.raises(TokenError):
        verifier.verify(make_token(UID, kid="rotated"))
    assert calls["n"] == 1
    now["t"] += 31
    keys.append({**_PUBLIC_JWK, "kid": "rotated"})
    verifier.verify(make_token(UID, kid="rotated"))
    assert calls["n"] == 2


def test_api_requires_a_bearer_token(client_for: ClientFor) -> None:
    anon = client_for(None)
    res = anon.get(f"{V1}/farms")
    body = err(res, 401, "unauthorized")
    assert res.headers["www-authenticate"] == "Bearer"
    assert "Sign in" in body["message"]
    err(client_for(None, token="garbage").get(f"{V1}/me"), 401, "unauthorized")
    expired = make_token(UID, "x@example.com", expires_in=-120)
    assert "expired" in err(client_for(None, token=expired).get(f"{V1}/me"), 401, "unauthorized")["message"]
    # System endpoints stay public (load balancer / status page).
    ok(anon.get(f"{V1}/health"))


def test_role_comes_from_database_not_token(client_for: ClientFor) -> None:
    sneaky = make_token(
        UID, "sneaky@example.com", user_metadata={"role": "admin"}, app_metadata={"role": "admin"}
    )
    client = client_for(None, token=sneaky)
    assert ok(client.get(f"{V1}/me"))["role"] == "farmer"
    err(client.get(f"{V1}/users"), 403, "forbidden")


def test_email_change_in_supabase_is_synced(client_for: ClientFor) -> None:
    ok(client_for(None, token=make_token(UID, "old@example.com")).get(f"{V1}/me"))
    me = ok(client_for(None, token=make_token(UID, "new@example.com")).get(f"{V1}/me"))
    assert me["email"] == "new@example.com"


def test_email_already_linked_to_another_account(client_for: ClientFor) -> None:
    ok(client_for(None, token=make_token(UID, "taken@example.com")).get(f"{V1}/me"))
    other = make_token(uuid.uuid4(), "taken@example.com")
    err(client_for(None, token=other).get(f"{V1}/me"), 401, "unauthorized")


def test_admin_user_management(admin: TestClient, api: TestClient) -> None:
    me = ok(api.get(f"{V1}/me"))
    users = ok(admin.get(f"{V1}/users"))
    assert {u["email"] for u in users["items"]} >= {"admin@example.com", "owner@example.com"}
    promoted = ok(admin.patch(f"{V1}/users/{me['id']}", json={"role": "agronomist"}))
    assert promoted["role"] == "agronomist"
    err(api.get(f"{V1}/users/{me['id']}"), 403, "forbidden")
