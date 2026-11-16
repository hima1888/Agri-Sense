"""Authentication dependencies: who is calling, and are they allowed to.

Identity comes only from a verified Supabase access token. Authorization data
(the user's role) comes only from our own `users` table, never from token
metadata, because Supabase `user_metadata` is editable by the user themself.
"""

from functools import lru_cache
from typing import Annotated, ClassVar

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.exc import IntegrityError

from app.api.deps import DbSession
from app.api.errors import ApiError
from app.core.config import Settings, get_settings
from app.core.security import TokenError, TokenVerifier, http_jwks_fetcher
from app.models import User

_bearer = HTTPBearer(auto_error=False, description="Supabase access token")


class UnauthorizedError(ApiError):
    status_code = 401
    code = "unauthorized"
    headers: ClassVar[dict[str, str] | None] = {"WWW-Authenticate": "Bearer"}


class ForbiddenError(ApiError):
    status_code = 403
    code = "forbidden"


class AuthNotConfiguredError(ApiError):
    status_code = 503
    code = "auth_not_configured"


@lru_cache
def _verifier_for(
    issuer: str | None, audience: str, secret: str, jwks_url: str | None = None
) -> TokenVerifier:
    fetcher = http_jwks_fetcher(jwks_url) if jwks_url else None
    return TokenVerifier(issuer=issuer, audience=audience, hs256_secret=secret or None, jwks_fetcher=fetcher)


def get_verifier(settings: Annotated[Settings, Depends(get_settings)]) -> TokenVerifier:
    if not settings.auth_configured:
        raise AuthNotConfiguredError("Authentication is not configured on this server (set SUPABASE_URL).")
    return _verifier_for(
        settings.auth_issuer, settings.supabase_jwt_audience, settings.supabase_jwt_secret, settings.jwks_url
    )


def get_current_user(
    db: DbSession,
    verifier: Annotated[TokenVerifier, Depends(get_verifier)],
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    if creds is None or creds.scheme.lower() != "bearer":
        raise UnauthorizedError("Sign in required.")
    try:
        claims = verifier.verify(creds.credentials)
    except TokenError as exc:
        raise UnauthorizedError(str(exc)) from exc

    user = db.get(User, claims.user_id)
    if user is None:
        # First request from this Supabase account: create its AGRI-SENSE profile.
        if not claims.email:
            raise UnauthorizedError("Token has no email address.")
        user = User(id=claims.user_id, email=claims.email, role="farmer")
        db.add(user)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()  # a concurrent first request created it, or the email belongs to another account
            user = db.get(User, claims.user_id)
            if user is None:
                raise UnauthorizedError("This email is already linked to a different account.") from None
    elif claims.email and user.email != claims.email:
        user.email = claims.email  # keep in sync when the address is changed in Supabase
        db.commit()

    db.info["actor_id"] = user.id  # picked up by audit logging
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_admin(user: CurrentUser) -> User:
    if user.role != "admin":
        raise ForbiddenError("Administrator role required.")
    return user


AdminUser = Annotated[User, Depends(require_admin)]
