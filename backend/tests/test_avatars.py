"""Profile picture upload, replacement and removal."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from app.db.mongo import Collections
from app.services.avatars import AVATAR_MAX_MB, AVATAR_PX
from app.services.storage import get_storage


def png_bytes(size=(400, 300), colour=(200, 40, 40), mode="RGB") -> bytes:
    img = Image.new(mode, size, colour if mode == "RGB" else (*colour, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


async def stored_key(db, user_id: str) -> str | None:
    doc = await db[Collections.USERS].find_one({"user_id": user_id}, {"_id": 0})
    return doc.get("avatar_key")


async def test_upload_sets_the_avatar(client, user, db):
    resp = await client.post(
        "/auth/me/avatar", headers=user["headers"],
        files={"file": ("me.png", png_bytes(), "image/png")},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["avatar_url"]

    me = await client.get("/auth/me", headers=user["headers"])
    assert me.json()["avatar_url"] == resp.json()["avatar_url"]

    key = await stored_key(db, user["user_id"])
    # Stored under the tenant prefix like every other object (TC-12).
    assert key and key.startswith(f"{user['user_id']}/")


async def test_stored_avatar_is_a_square_thumbnail(client, user, db):
    await client.post(
        "/auth/me/avatar", headers=user["headers"],
        files={"file": ("wide.png", png_bytes(size=(1200, 400)), "image/png")},
    )
    key = await stored_key(db, user["user_id"])
    img = Image.open(io.BytesIO(get_storage().read_bytes(key)))
    assert img.size == (AVATAR_PX, AVATAR_PX)


async def test_transparency_flattens_to_white_not_black(client, user, db):
    """convert("RGB") would composite onto black and give a cut-out a dark box."""
    await client.post(
        "/auth/me/avatar", headers=user["headers"],
        files={"file": ("cut.png", png_bytes(mode="RGBA"), "image/png")},
    )
    key = await stored_key(db, user["user_id"])
    img = Image.open(io.BytesIO(get_storage().read_bytes(key))).convert("RGB")
    assert img.getpixel((4, 4)) == (255, 255, 255)


async def test_replacing_drops_the_previous_object(client, user, db):
    first = await client.post(
        "/auth/me/avatar", headers=user["headers"],
        files={"file": ("a.png", png_bytes(colour=(10, 200, 10)), "image/png")},
    )
    old_key = await stored_key(db, user["user_id"])

    second = await client.post(
        "/auth/me/avatar", headers=user["headers"],
        files={"file": ("b.png", png_bytes(colour=(10, 10, 200)), "image/png")},
    )
    new_key = await stored_key(db, user["user_id"])

    assert new_key != old_key
    # The key is a content hash, so a new picture must be a new URL -- a stable
    # path would keep serving the previous face out of cache.
    assert second.json()["avatar_url"] != first.json()["avatar_url"]
    assert not get_storage().exists(old_key)


async def test_reuploading_the_same_image_keeps_it(client, user, db):
    """Same bytes hash to the same key; cleanup must not delete what it just wrote."""
    data = png_bytes(colour=(90, 90, 200))
    for _ in range(2):
        resp = await client.post(
            "/auth/me/avatar", headers=user["headers"],
            files={"file": ("same.png", data, "image/png")},
        )
        assert resp.status_code == 200

    key = await stored_key(db, user["user_id"])
    assert get_storage().exists(key)


async def test_delete_clears_it(client, user, db):
    await client.post(
        "/auth/me/avatar", headers=user["headers"],
        files={"file": ("me.png", png_bytes(), "image/png")},
    )
    key = await stored_key(db, user["user_id"])

    resp = await client.delete("/auth/me/avatar", headers=user["headers"])
    assert resp.status_code == 200
    assert resp.json()["avatar_url"] is None
    assert await stored_key(db, user["user_id"]) is None
    assert not get_storage().exists(key)


@pytest.mark.parametrize(
    ("name", "data", "expected"),
    [
        ("doc.pdf", b"%PDF-1.4\n" + b"0" * 64, "png, jpg, or webp"),
        ("junk.png", b"not an image at all, really", "invalid file format"),
        ("empty.png", b"", "empty"),
    ],
)
async def test_rejects_what_is_not_a_picture(client, user, name, data, expected):
    resp = await client.post(
        "/auth/me/avatar", headers=user["headers"],
        files={"file": (name, data, "application/octet-stream")},
    )
    assert resp.status_code == 400, resp.text
    assert expected in resp.json()["detail"].lower()


async def test_rejects_oversized_upload(client, user):
    resp = await client.post(
        "/auth/me/avatar", headers=user["headers"],
        files={"file": ("big.png", b"\x89PNG\r\n\x1a\n" + b"0" * (AVATAR_MAX_MB * 1024 * 1024),
                        "image/png")},
    )
    assert resp.status_code == 400
    assert f"under {AVATAR_MAX_MB}mb" in resp.json()["detail"].lower()


async def test_requires_authentication(client):
    resp = await client.post(
        "/auth/me/avatar", files={"file": ("me.png", png_bytes(), "image/png")},
    )
    assert resp.status_code == 401
