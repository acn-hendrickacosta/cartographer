"""Direct login (app/auth.py's direct_login, POST /api/login) -- the
ADMIN_USER_PASSWORD_AUTH alternative to the hosted-UI redirect, added because
the hosted UI requires an HTTPS callback_url that this deployment doesn't
have. Covers SECRET_HASH computation, the Cognito API call, challenge
rejection, and the route's session-setting behavior, all mocked -- no real
Cognito or network access needed.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import auth
from app.main import app

client = TestClient(app)


def _secret_hash(username: str) -> str:
    message = (username + "test-client-id").encode("utf-8")
    key = "test-client-secret".encode("utf-8")
    return base64.b64encode(hmac.new(key, message, hashlib.sha256).digest()).decode("utf-8")


def test_secret_hash_matches_cognito_algorithm():
    assert auth._secret_hash("alice@example.com") == _secret_hash("alice@example.com")


def test_direct_login_success_returns_session_user():
    fake_resp = {"AuthenticationResult": {"IdToken": "fake-id-token"}}
    fake_user = auth.SessionUser(email="alice@example.com", groups=["Author"])
    with patch.object(auth._cognito, "admin_initiate_auth", return_value=fake_resp) as mock_auth, \
         patch.object(auth, "verify_id_token", return_value=fake_user) as mock_verify:
        result = auth.direct_login("alice@example.com", "s3cr3t")

    assert result is fake_user
    mock_verify.assert_called_once_with("fake-id-token")
    call_kwargs = mock_auth.call_args.kwargs
    assert call_kwargs["AuthFlow"] == "ADMIN_USER_PASSWORD_AUTH"
    assert call_kwargs["AuthParameters"]["USERNAME"] == "alice@example.com"
    assert call_kwargs["AuthParameters"]["PASSWORD"] == "s3cr3t"
    assert call_kwargs["AuthParameters"]["SECRET_HASH"] == _secret_hash("alice@example.com")


def test_direct_login_wrong_password_raises_401():
    error = ClientError({"Error": {"Code": "NotAuthorizedException", "Message": "bad creds"}}, "AdminInitiateAuth")
    with patch.object(auth._cognito, "admin_initiate_auth", side_effect=error):
        with pytest.raises(HTTPException) as exc_info:
            auth.direct_login("alice@example.com", "wrong")
    assert exc_info.value.status_code == 401


def test_direct_login_challenge_raises_401_not_supported():
    fake_resp = {"ChallengeName": "NEW_PASSWORD_REQUIRED"}
    with patch.object(auth._cognito, "admin_initiate_auth", return_value=fake_resp):
        with pytest.raises(HTTPException) as exc_info:
            auth.direct_login("alice@example.com", "temp-password")
    assert exc_info.value.status_code == 401
    assert "NEW_PASSWORD_REQUIRED" in exc_info.value.detail


def test_api_login_route_sets_session_and_returns_user():
    fake_user = auth.SessionUser(email="alice@example.com", groups=["Author", "Reviewer"])
    with patch.object(auth, "direct_login", return_value=fake_user):
        resp = client.post("/api/login", json={"email": "alice@example.com", "password": "s3cr3t"})

    assert resp.status_code == 200
    assert resp.json() == {"email": "alice@example.com", "groups": ["Author", "Reviewer"]}

    # Session cookie was actually set -- /api/me now succeeds without logging in again.
    me = client.get("/api/me")
    assert me.status_code == 200
    assert me.json() == {"email": "alice@example.com", "groups": ["Author", "Reviewer"]}
    client.cookies.clear()


def test_api_login_route_propagates_401_on_bad_credentials():
    with patch.object(auth, "direct_login", side_effect=HTTPException(status_code=401, detail="invalid email or password")):
        resp = client.post("/api/login", json={"email": "alice@example.com", "password": "wrong"})
    assert resp.status_code == 401


def test_logout_clears_session_without_cognito_redirect():
    fake_user = auth.SessionUser(email="alice@example.com", groups=[])
    with patch.object(auth, "direct_login", return_value=fake_user):
        client.post("/api/login", json={"email": "alice@example.com", "password": "s3cr3t"})

    resp = client.get("/logout", follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert resp.headers["location"] == "/"

    me = client.get("/api/me")
    assert me.status_code == 401
    client.cookies.clear()
