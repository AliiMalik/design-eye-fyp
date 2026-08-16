"""Pytest fixtures.

Tests run against a real MongoDB and the real model: the point of TC-06 through
TC-09 is that the actual inference path produces the expected numbers, which a
mocked model would not prove.
"""

from __future__ import annotations

import io
import os
import uuid
from pathlib import Path

import pytest

# Must be set before app.config is imported anywhere.
os.environ.setdefault("MONGODB_DB", "designeye_test")
os.environ.setdefault("DEV_MODE", "true")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("JWT_SECRET", "test-secret-not-for-production")
os.environ.setdefault("STORAGE_LOCAL_DIR", "./storage_test")
# The suite registers dozens of accounts; the production 10/minute ceiling would
# throttle the tests themselves. Rate limiting is asserted separately below.
os.environ.setdefault("AUTH_RATE_LIMIT", "5000/minute")

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

from app.config import settings  # noqa: E402
from app.db.mongo import Collections  # noqa: E402
from app.main import app  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "slow: exercises real model inference")


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def client():
    """One ASGI client with the app's real lifespan (model + DB + indexes)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as ac:
        async with app.router.lifespan_context(app):
            yield ac


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def db():
    from app.db.mongo import get_database

    return get_database()


@pytest.fixture
def unique_email() -> str:
    return f"user-{uuid.uuid4().hex[:12]}@designeye.dev"


@pytest_asyncio.fixture(loop_scope="session")
async def user(client, unique_email):
    """A registered user with auth headers ready to use."""
    resp = await client.post("/auth/register", json={
        "email": unique_email, "password": "Test@1234", "display_name": "Test User",
    })
    assert resp.status_code == 201, resp.text
    data = resp.json()
    return {
        "email": unique_email,
        "password": "Test@1234",
        "user_id": data["user"]["user_id"],
        "access_token": data["access_token"],
        "refresh_token": data["refresh_token"],
        "headers": {"Authorization": f"Bearer {data['access_token']}"},
    }


@pytest_asyncio.fixture(loop_scope="session")
async def other_user(client):
    """A second, unrelated tenant used to prove isolation (TC-12)."""
    email = f"other-{uuid.uuid4().hex[:12]}@designeye.dev"
    resp = await client.post("/auth/register", json={
        "email": email, "password": "Other@1234",
    })
    assert resp.status_code == 201
    data = resp.json()
    return {
        "user_id": data["user"]["user_id"],
        "headers": {"Authorization": f"Bearer {data['access_token']}"},
    }


# --- image helpers ---------------------------------------------------------
def make_png(width: int = 900, height: int = 600, *, clean: bool = True) -> bytes:
    """Synthesise a clean or cluttered mockup as PNG bytes."""
    img = Image.new("RGB", (width, height), (255, 255, 255))
    d = ImageDraw.Draw(img)

    if clean:
        d.rectangle([int(width * 0.3), int(height * 0.3),
                     int(width * 0.7), int(height * 0.4)], fill=(15, 15, 15))
        d.rectangle([int(width * 0.42), int(height * 0.55),
                     int(width * 0.58), int(height * 0.63)], fill=(79, 91, 213))
    else:
        import random

        rng = random.Random(7)
        for _ in range(320):
            x, y = rng.randint(0, width - 40), rng.randint(0, height - 30)
            d.rectangle([x, y, x + rng.randint(20, 120), y + rng.randint(10, 40)],
                        fill=(rng.randint(0, 220), rng.randint(0, 220), rng.randint(0, 220)),
                        outline=(10, 10, 10))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def clean_png() -> bytes:
    return make_png(clean=True)


@pytest.fixture
def cluttered_png() -> bytes:
    return make_png(clean=False)


@pytest.fixture
def sample_paths() -> dict[str, list[Path]]:
    """Calibration samples, when they have been generated."""
    base = ROOT / "inputs" / "samples"
    return {
        "clean": sorted((base / "clean").glob("*.png")) if (base / "clean").is_dir() else [],
        "cluttered": sorted((base / "cluttered").glob("*.png"))
        if (base / "cluttered").is_dir() else [],
    }


async def upload_and_wait(client, headers, data: bytes, filename="mockup.png",
                          project_id: str | None = None, timeout_s: int = 120):
    """Upload a mockup and poll until the task settles. Returns (asset_id, status)."""
    import asyncio

    files = {"file": (filename, data, "image/png")}
    form = {"project_id": project_id} if project_id else None
    resp = await client.post("/upload", headers=headers, files=files, data=form)
    assert resp.status_code == 202, resp.text
    payload = resp.json()

    for _ in range(timeout_s * 2):
        status = (await client.get(f"/status/{payload['task_id']}", headers=headers)).json()
        if status["status"] in ("complete", "failed"):
            return payload["asset_id"], status
        await asyncio.sleep(0.5)

    raise AssertionError("inference task did not settle in time")
