"""Cascade deletion for analysis artefacts.

Deleting a result, a batch, or a project all have to remove the same derived
objects: the stored upload, the heatmap PNG, the saliency array, the result
document, the inference tasks, and the cached suggestions. Written out three
times separately they drifted -- the project delete removed the documents but
left every stored file and every SuggestionDoc behind, permanently unreachable
because the documents holding the storage keys had just been dropped. One
function now, called by all three, so a fourth caller cannot repeat it.
"""

from __future__ import annotations

import logging

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db.mongo import Collections
from app.services.storage import StorageService, get_storage

logger = logging.getLogger(__name__)


def _drop(storage: StorageService, key: str | None) -> None:
    """Remove one stored object.

    Best effort: a storage backend that refuses to delete must not abort the
    database cleanup, or the user is left staring at a row they cannot remove.
    An orphaned object is untidy; an undeletable project is a broken product.
    """
    if not key:
        return
    try:
        storage.delete(key)
    except Exception as exc:  # noqa: BLE001 - cleanup continues regardless
        logger.warning("Could not delete stored object %s: %s", key, exc)


async def purge_assets(db: AsyncIOMotorDatabase, asset_ids: list[str],
                       storage: StorageService | None = None) -> None:
    """Delete these assets and everything derived from them.

    Storage objects are removed FIRST. Their keys live on the very documents
    being deleted, so dropping the documents first strands the files with
    nothing left in the system pointing at them.
    """
    if not asset_ids:
        return
    storage = storage or get_storage()

    assets = await db[Collections.MOCKUP_ASSETS].find(
        {"asset_id": {"$in": asset_ids}}, {"_id": 0, "storage_key": 1},
    ).to_list(length=None)
    results = await db[Collections.HEATMAP_RESULTS].find(
        {"asset_id": {"$in": asset_ids}},
        {"_id": 0, "result_id": 1, "storage_keys": 1},
    ).to_list(length=None)

    for asset in assets:
        _drop(storage, asset.get("storage_key"))
    for result in results:
        for key in (result.get("storage_keys") or {}).values():
            _drop(storage, key)

    result_ids = [r["result_id"] for r in results if r.get("result_id")]
    if result_ids:
        await db[Collections.SUGGESTIONS].delete_many(
            {"result_id": {"$in": result_ids}})

    await db[Collections.HEATMAP_RESULTS].delete_many({"asset_id": {"$in": asset_ids}})
    await db[Collections.INFERENCE_TASKS].delete_many({"asset_id": {"$in": asset_ids}})
    await db[Collections.MOCKUP_ASSETS].delete_many({"asset_id": {"$in": asset_ids}})

    logger.info("Purged %d asset(s), %d result(s), %d suggestion doc(s)",
                len(assets), len(results), len(result_ids))
