"""Authentication test cases: TC-01, TC-02, TC-11, TC-14."""

from __future__ import annotations

import time
import uuid

import jwt
import pytest

from app.config import settings


async def test_tc01_register_valid_credentials(client):
    """TC-01: account created and a JWT returned."""
    email = f"tc01-{uuid.uuid4().hex[:10]}@designeye.dev"
    resp = await client.post("/auth/register", json={
        "email": email, "password": "Valid@1234", "display_name": "TC One",
    })

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["access_token"] and body["refresh_token"]
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == email
    assert body["user"]["user_id"]
    # The hash must never travel to the client.
    assert "password" not in resp.text.lower() or "password_hash" not in resp.text


async def test_tc02_duplicate_email_rejected(client):
    """TC-02: a second registration with the same email fails, no duplicate row."""
    email = f"tc02-{uuid.uuid4().hex[:10]}@designeye.dev"
    first = await client.post("/auth/register", json={"email": email, "password": "Valid@1234"})
    assert first.status_code == 201

    second = await client.post("/auth/register", json={"email": email, "password": "Other@1234"})
    assert second.status_code == 409
    assert "already in use" in second.json()["detail"].lower()


async def test_tc02_duplicate_is_case_insensitive(client):
    email = f"tc02b-{uuid.uuid4().hex[:10]}@designeye.dev"
    assert (await client.post("/auth/register",
                              json={"email": email, "password": "Valid@1234"})).status_code == 201
    dupe = await client.post("/auth/register",
                             json={"email": email.upper(), "password": "Valid@1234"})
    assert dupe.status_code == 409


async def test_password_never_stored_in_plaintext(client, db, unique_email):
    resp = await client.post("/auth/register",
                             json={"email": unique_email, "password": "Secret@1234"})
    assert resp.status_code == 201

    doc = await db["users"].find_one({"email": unique_email})
    assert doc is not None
    assert "Secret@1234" not in str(doc)
    assert doc["password_hash"].startswith("$2b$")  # bcrypt
    # cost factor 12, as required by BUILD.md section 9
    assert doc["password_hash"].split("$")[2] == "12"


async def test_login_success_and_wrong_password(client, user):
    ok = await client.post("/auth/login",
                           json={"email": user["email"], "password": user["password"]})
    assert ok.status_code == 200
    assert ok.json()["access_token"]

    bad = await client.post("/auth/login",
                            json={"email": user["email"], "password": "Wrong@9999"})
    assert bad.status_code == 401


async def test_login_unknown_email_is_indistinguishable(client):
    """Wrong password and unknown account must return the same message."""
    unknown = await client.post("/auth/login",
                                json={"email": "nobody@designeye.dev", "password": "Any@1234"})
    assert unknown.status_code == 401
    assert unknown.json()["detail"] == "Invalid email or password."


async def test_weak_password_rejected(client, unique_email):
    for weak in ("short1", "alllettersonly", "12345678"):
        resp = await client.post("/auth/register",
                                 json={"email": unique_email, "password": weak})
        assert resp.status_code == 422, weak


@pytest.mark.parametrize("path", ["/results", "/projects", "/dashboard", "/compare"])
async def test_tc11_unauthenticated_requests_rejected(client, path):
    """TC-11: no JWT -> 401."""
    assert (await client.get(path)).status_code == 401


async def test_tc11_upload_without_token_is_rejected(client, clean_png):
    resp = await client.post("/upload", files={"file": ("m.png", clean_png, "image/png")})
    assert resp.status_code == 401


async def test_tc14_expired_token_returns_401(client, user):
    """TC-14: an expired session JWT is refused."""
    expired = jwt.encode(
        {
            "sub": user["user_id"],
            "type": "access",
            "jti": str(uuid.uuid4()),
            "iat": int(time.time()) - 7200,
            "exp": int(time.time()) - 3600,
        },
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )
    resp = await client.get("/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert resp.status_code == 401
    assert "expired" in resp.json()["detail"].lower()


async def test_tc14_malformed_and_wrongly_signed_tokens_rejected(client, user):
    assert (await client.get("/auth/me",
                             headers={"Authorization": "Bearer not.a.jwt"})).status_code == 401

    forged = jwt.encode(
        {"sub": user["user_id"], "type": "access", "jti": "x",
         "iat": int(time.time()), "exp": int(time.time()) + 3600},
        "the-wrong-secret", algorithm="HS256",
    )
    assert (await client.get("/auth/me",
                             headers={"Authorization": f"Bearer {forged}"})).status_code == 401


async def test_refresh_token_cannot_be_used_as_access_token(client, user):
    resp = await client.get(
        "/auth/me", headers={"Authorization": f"Bearer {user['refresh_token']}"})
    assert resp.status_code == 401


async def test_refresh_rotates_access_token(client, user):
    resp = await client.post("/auth/refresh", json={"refresh_token": user["refresh_token"]})
    assert resp.status_code == 200
    assert resp.json()["access_token"]


async def test_logout_denylists_the_refresh_token(client, user):
    out = await client.post("/auth/logout", headers=user["headers"],
                            json={"refresh_token": user["refresh_token"]})
    assert out.status_code == 200

    reused = await client.post("/auth/refresh", json={"refresh_token": user["refresh_token"]})
    assert reused.status_code == 401
    assert "revoked" in reused.json()["detail"].lower()


async def test_me_and_profile_update(client, user):
    me = await client.get("/auth/me", headers=user["headers"])
    assert me.status_code == 200
    assert me.json()["email"] == user["email"]

    patched = await client.patch("/auth/me", headers=user["headers"],
                                 json={"display_name": "Renamed", "bio": "A bio."})
    assert patched.status_code == 200
    assert patched.json()["display_name"] == "Renamed"


async def test_password_reset_flow(client, user):
    started = await client.post("/auth/reset-password", json={"email": user["email"]})
    assert started.status_code == 200
    # DEV_MODE returns the token inline because there is no mail service.
    token = started.json()["message"].split("DEV_MODE token:")[-1].strip()
    assert token

    confirmed = await client.post("/auth/reset-password/confirm",
                                  json={"token": token, "new_password": "Rotated@1234"})
    assert confirmed.status_code == 200

    assert (await client.post("/auth/login",
                              json={"email": user["email"],
                                    "password": "Rotated@1234"})).status_code == 200
    assert (await client.post("/auth/login",
                              json={"email": user["email"],
                                    "password": user["password"]})).status_code == 401


async def test_reset_for_unknown_email_does_not_leak(client):
    resp = await client.post("/auth/reset-password",
                             json={"email": "ghost@designeye.dev"})
    assert resp.status_code == 200
    assert "DEV_MODE token" not in resp.json()["message"]


async def test_auth_endpoints_are_rate_limited(client):
    """The limiter is installed and wraps register + login (BUILD.md s9)."""
    from app.api.v1.auth import limiter, login, register
    from app.main import app

    assert app.state.limiter is limiter
    assert settings.AUTH_RATE_LIMIT

    # slowapi replaces the endpoint, leaving the original on __wrapped__.
    assert hasattr(register, "__wrapped__"), "register is not rate limited"
    assert hasattr(login, "__wrapped__"), "login is not rate limited"

    # keys are fully-qualified, e.g. "app.api.v1.auth.register"
    marked = {k.rsplit(".", 1)[-1] for k in limiter._Limiter__marked_for_limiting}
    assert {"register", "login"} <= marked, f"only these are limited: {marked}"


async def test_cors_is_an_allow_list_not_wildcard():
    assert "*" not in settings.cors_origin_list
    assert settings.cors_origin_list
