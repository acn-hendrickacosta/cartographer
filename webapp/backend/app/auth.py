"""Cognito authentication: hosted-UI OAuth2 authorization-code flow for the
human-facing screens, plus JWKS-based ID token verification.

Role comes from the Cognito group the user is a member of (Author/Reviewer/
Admin, per APPLICATION_ARCHITECTURE.md Sec 2.2 -- "a user can hold more than
one role", so this is a list, not a single value), read from the ID token's
`cognito:groups` claim.

Also supports a second login path, direct_login() below: Cognito's
ADMIN_USER_PASSWORD_AUTH flow, called directly via boto3 instead of a browser
redirect to the hosted UI. Added because the hosted-UI flow requires an HTTPS
callback URL -- Cognito rejects any non-localhost HTTP redirect_uri outright
-- which this deployment doesn't have yet (see the ECS deployment plan's
"ALB's own default DNS name" gap). direct_login never touches a redirect_uri
at all: it's a server-to-server call to Cognito's API (always HTTPS,
independent of how the user's own browser reaches this app), so it works
over plain HTTP. verify_id_token below is unchanged and reused as-is -- a
Cognito ID token is a Cognito ID token regardless of which flow produced it.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from urllib.parse import urlencode

import boto3
import httpx
import jwt
from botocore.exceptions import ClientError
from fastapi import HTTPException, Request
from jwt import PyJWKClient

from app.settings import settings

_jwk_client = PyJWKClient(settings.cognito_jwks_url)
_cognito = boto3.client("cognito-idp", region_name=settings.aws_region)


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


def _secret_hash(username: str) -> str:
    """Cognito requires this whenever the app client has a secret (ours
    does), for any API-based auth flow -- HMAC-SHA256 of username+client_id,
    keyed by the client secret, base64-encoded. Not needed for the hosted-UI
    flow, which authenticates the client via Basic auth instead (see
    exchange_code_for_tokens above)."""
    message = (username + settings.cognito_client_id).encode("utf-8")
    key = settings.cognito_client_secret.encode("utf-8")
    digest = hmac.new(key, message, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def direct_login(email: str, password: str) -> SessionUser:
    """ADMIN_USER_PASSWORD_AUTH: exchange an email/password directly for a
    verified SessionUser, no browser redirect involved. Raises
    HTTPException(401) for bad credentials, same as the hosted-UI path's
    failure mode -- a wrong password is a client error, not a server error."""
    try:
        resp = _cognito.admin_initiate_auth(
            UserPoolId=settings.cognito_pool_id,
            ClientId=settings.cognito_client_id,
            AuthFlow="ADMIN_USER_PASSWORD_AUTH",
            AuthParameters={
                "USERNAME": email,
                "PASSWORD": password,
                "SECRET_HASH": _secret_hash(email),
            },
        )
    except ClientError as exc:
        raise HTTPException(status_code=401, detail="invalid email or password") from exc

    if resp.get("ChallengeName"):
        # e.g. NEW_PASSWORD_REQUIRED for a user still on a temporary password.
        # Not handled -- this path is for already-provisioned users with a
        # permanent password (the seeded test users, or anyone an Admin has
        # set up via AdminSetUserPassword with Permanent=True).
        raise HTTPException(
            status_code=401,
            detail=f"login requires completing the '{resp['ChallengeName']}' challenge, not supported here",
        )

    id_token = resp["AuthenticationResult"]["IdToken"]
    try:
        return verify_id_token(id_token)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail=f"id token verification failed: {exc}") from exc


def current_user(request: Request) -> SessionUser:
    data = request.session.get("user")
    if not data:
        raise HTTPException(status_code=401, detail="not logged in")
    return SessionUser.from_session_dict(data)
