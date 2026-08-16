"""Storage abstraction: local filesystem (default) or Cloudinary.

Every object key is prefixed with the owning ``user_id`` so tenants stay
isolated on disk as well as in the database (BUILD.md section 9).
"""

from __future__ import annotations

import io
import logging
import shutil
from abc import ABC, abstractmethod
from pathlib import Path

import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)


class StorageService(ABC):
    """Interface every storage backend implements."""

    @abstractmethod
    def save_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        """Persist raw bytes at ``key`` and return a retrievable URL."""

    @abstractmethod
    def read_bytes(self, key: str) -> bytes:
        """Read the object back."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Remove an object; missing objects are not an error."""

    @abstractmethod
    def url_for(self, key: str) -> str:
        """Public URL for an existing key."""

    @abstractmethod
    def exists(self, key: str) -> bool:
        ...

    # -- shared helpers ---------------------------------------------------
    def save_npy(self, key: str, array: np.ndarray) -> str:
        buf = io.BytesIO()
        np.save(buf, array.astype(np.float32), allow_pickle=False)
        return self.save_bytes(key, buf.getvalue(), "application/octet-stream")

    def read_npy(self, key: str) -> np.ndarray:
        return np.load(io.BytesIO(self.read_bytes(key)), allow_pickle=False)

    @staticmethod
    def tenant_key(user_id: str, *parts: str) -> str:
        return "/".join([user_id, *parts])


class LocalStorage(StorageService):
    """Files under ``STORAGE_LOCAL_DIR``, served by the API's /storage mount."""

    def __init__(self, root: str | Path | None = None, base_url: str | None = None):
        self.root = Path(root or settings.STORAGE_LOCAL_DIR).resolve()
        self.base_url = (base_url or settings.PUBLIC_BASE_URL).rstrip("/")
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        # Reject traversal: the resolved path must stay under the root.
        target = (self.root / key).resolve()
        if not str(target).startswith(str(self.root)):
            raise ValueError(f"Refusing to write outside the storage root: {key}")
        return target

    def save_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return self.url_for(key)

    def read_bytes(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path, ignore_errors=True)

    def url_for(self, key: str) -> str:
        return f"{self.base_url}/storage/{key}"

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()


class CloudinaryStorage(StorageService):
    """Cloudinary backend, enabled with STORAGE_BACKEND=cloudinary."""

    def __init__(self) -> None:
        import cloudinary  # imported lazily so local runs need no credentials
        import cloudinary.api
        import cloudinary.uploader

        cloudinary.config(
            cloud_name=settings.CLOUDINARY_CLOUD_NAME,
            api_key=settings.CLOUDINARY_API_KEY,
            api_secret=settings.CLOUDINARY_API_SECRET,
            secure=True,
        )
        self._uploader = cloudinary.uploader
        self._api = cloudinary.api
        self._cloudinary = cloudinary

    # Cloudinary splits its namespace by resource_type, and the two types
    # address objects differently: an image's public_id excludes the extension
    # (the format is appended at delivery), while a raw object's public_id is
    # the full filename. Deriving both from the key in ONE place is what keeps
    # upload, URL, existence, and delete addressing the same object -- get it
    # wrong for .npy and reruns and A/B comparison silently break.
    RAW_SUFFIXES = (".npy",)

    @classmethod
    def _address(cls, key: str) -> tuple[str, str, str | None]:
        """Return (resource_type, public_id, image_format) for a storage key."""
        if key.lower().endswith(cls.RAW_SUFFIXES):
            return "raw", key, None
        base, _, ext = key.rpartition(".")
        if not base:  # no extension at all
            return "image", key, None
        return "image", base, ext.lower()

    def save_bytes(self, key: str, data: bytes,
                   content_type: str = "application/octet-stream") -> str:
        resource_type, public_id, _ = self._address(key)
        result = self._uploader.upload(
            io.BytesIO(data),
            public_id=public_id,
            resource_type=resource_type,
            overwrite=True,
            invalidate=True,
            use_filename=False,
            unique_filename=False,
        )
        return result["secure_url"]

    def read_bytes(self, key: str) -> bytes:
        import httpx

        resp = httpx.get(self.url_for(key), timeout=30, follow_redirects=True)
        resp.raise_for_status()
        return resp.content

    def delete(self, key: str) -> None:
        resource_type, public_id, _ = self._address(key)
        try:
            self._uploader.destroy(public_id, resource_type=resource_type,
                                   invalidate=True)
        except Exception as exc:  # noqa: BLE001 - deletion is best-effort
            logger.warning("Cloudinary delete failed for %s: %s", key, exc)

    def url_for(self, key: str) -> str:
        resource_type, public_id, fmt = self._address(key)
        url, _ = self._cloudinary.utils.cloudinary_url(
            public_id, resource_type=resource_type, format=fmt, secure=True,
        )
        return url

    def exists(self, key: str) -> bool:
        resource_type, public_id, _ = self._address(key)
        try:
            self._api.resource(public_id, resource_type=resource_type)
            return True
        except Exception:  # noqa: BLE001
            return False


_storage: StorageService | None = None


def get_storage() -> StorageService:
    """Process-wide storage singleton selected by STORAGE_BACKEND."""
    global _storage
    if _storage is None:
        if settings.STORAGE_BACKEND == "cloudinary":
            _storage = CloudinaryStorage()
            logger.info("Storage backend: cloudinary")
        else:
            _storage = LocalStorage()
            logger.info("Storage backend: local (%s)", settings.STORAGE_LOCAL_DIR)
    return _storage
