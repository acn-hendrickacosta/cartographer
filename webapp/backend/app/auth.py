"""Cognito authentication: hosted-UI OAuth2 authorization-code flow for the
human-facing screens, plus JWKS-based ID token verification.

Role comes from the Cognito group the user is a member of (Author/Reviewer/
Admin, per APPLICATION_ARCHITECTURE.md Sec 2.2 -- "a user can hold more than
one role", so this is a list, not a single value), read from the ID token's
`cognito:groups` claim.
"""

from __future__ import annotations

from urllib.parse import urlencode

import httpx
import jwt
from fastapi import HTTPException, Request
from jwt import PyJWKClient

from app.settings import settings

_jwk_client = PyJWKClient(settings.cognito_jwks_url)


class SessionUser:
    def __init__(self, email: str, groups: list[str]):
        self.email = email
        self.groups = groups

    def has_role(self, role: str) -> bool:
        return role in self.groups

    def to_session_dict(self) -> dict:
        return {"email": self.email, "groups": self.groups}

    @classmethod
    def from_session_dict(cls, data: dict) -> "SessionUser":
        return cls(email=data["email"], groups=data["groups"])


def verify_id_token(id_token: str) -> SessionUser:
    """Verify a Cognito ID token's signature, issuer, and audience, and
    extract the user's email + group memberships. Raises jwt exceptions on
    any verification failure -- callers should let those surface as 401s."""
    signing_key = _jwk_client.get_signing_key_from_jwt(id_token)
    claims = jwt.decode(
        id_token,
        signing_key.key,
        algorithms=["RS256"],
        audience=settings.cognito_client_id,
        issuer=settings.cognito_issuer,
    )
    return SessionUser(email=claims["email"], groups=claims.get("cognito:groups", []))


def hosted_ui_login_url(state: str = "") -> str:
    params = {
        "client_id": settings.cognito_client_id,
        "response_type": "code",
        "scope": "openid email profile",
        "redirect_uri": settings.redirect_uri,
    }
    if state:
        params["state"] = state
    return f"{settings.cognito_hosted_ui_base}/oauth2/authorize?{urlencode(params)}"


def hosted_ui_logout_url() -> str:
    params = {"client_id": settings.cognito_client_id, "logout_uri": f"{settings.base_url}/"}
    return f"{settings.cognito_hosted_ui_base}/logout?{urlencode(params)}"


async def exchange_code_for_tokens(code: str) -> dict:
    """POST to Cognito's /oauth2/token endpoint, exchanging an authorization
    code for id_token/access_token/refresh_token. Raises HTTPException(401)
    on any failure -- a bad or expired code is a client error, not a server
    error worth a 500."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.cognito_hosted_ui_base}/oauth2/token",
            data={
                "grant_type": "authorization_code",
                "client_id": settings.cognito_client_id,
                "code": code,
                "redirect_uri": settings.redirect_uri,
            },
            auth=(settings.cognito_client_id, settings.cognito_client_secret),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail=f"token exchange failed: {resp.text}")
    return resp.json()


def current_user(request: Request) -> SessionUser:
    data = request.session.get("user")
    if not data:
        raise HTTPException(status_code=401, detail="not logged in")
    return SessionUser.from_session_dict(data)
