"""Per-user daily LLM allowance.

Shared by the single-screen and flow reviewers so the two can never drift into
counting differently. A whole flow is deliberately one unit: reviewing twelve
screens in one provider call costs one call, so it should cost one unit.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.config import settings
from app.db.mongo import Collections


async def consume_llm_quota(db, user_id: str) -> bool:
    """Charge one unit and report whether the user has now exceeded the cap.

    The increment happens first and unconditionally: an atomic
    find-and-increment is the only way to make the check race-free across
    concurrent requests.
    """
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    doc = await db[Collections.LLM_USAGE].find_one_and_update(
        {"user_id": user_id, "day": day},
        {"$inc": {"count": 1}},
        upsert=True, return_document=True,
    )
    return int((doc or {}).get("count", 0)) > settings.LLM_RATE_LIMIT_PER_DAY
