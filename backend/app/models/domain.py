"""MongoDB document models.

Field names follow the SDS schema tables (Tables 5-10). Documented additions
per BUILD.md section 7:
  users            + password_hash, role
  heatmap_results  + focus_index, clutter_index, region_saliency, user_id
  mockup_assets    + width, height
The SDS's Cloudinary-specific column names are storage-agnostic here
(``heatmap_url`` rather than ``heatmap_cloudinary_url``) because storage is a
pluggable backend; see docs/DEVIATIONS.md.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


class AssetStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETE = "complete"
    FAILED = "failed"


class TaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETE = "complete"
    FAILED = "failed"


class AssetFormat(str, Enum):
    PNG = "png"
    JPG = "jpg"
    JPEG = "jpeg"
    WEBP = "webp"
    SVG = "svg"
    PDF = "pdf"


class UserRole(str, Enum):
    DESIGNER = "designer"
    ADMIN = "admin"


class LLMStatus(str, Enum):
    OK = "ok"
    UNAVAILABLE = "unavailable"
    ERROR = "error"
    RATE_LIMITED = "rate_limited"


class MongoModel(BaseModel):
    model_config = ConfigDict(use_enum_values=True, populate_by_name=True)

    def to_mongo(self) -> dict[str, Any]:
        return self.model_dump(mode="python")


class User(MongoModel):
    user_id: str = Field(default_factory=new_id)
    email: EmailStr
    display_name: str | None = None
    password_hash: str                       # addition: Firebase is gone
    role: UserRole = UserRole.DESIGNER       # addition
    tenant_prefix: str = ""                  # equals user_id
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    is_active: bool = True
    bio: str | None = None


class Project(MongoModel):
    project_id: str = Field(default_factory=new_id)
    user_id: str
    title: str
    description: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class BatchStatus(str, Enum):
    PROCESSING = "processing"
    COMPLETE = "complete"
    PARTIAL = "partial"   # some screens failed, the rest are usable
    FAILED = "failed"


class ScreenBatch(MongoModel):
    """One multi-screen upload: a PDF fanned out into N assets."""

    batch_id: str = Field(default_factory=new_id)
    user_id: str
    project_id: str
    source_filename: str
    page_count: int
    pages_skipped: int = 0
    status: BatchStatus = BatchStatus.PROCESSING
    # Populated by the single batched LLM call.
    flow_summary: str = ""
    weakest_screen: int | None = None
    strongest_screen: int | None = None
    llm_status: LLMStatus | None = None
    llm_provider: str = ""
    llm_model: str = ""
    created_at: datetime = Field(default_factory=utcnow)


class MockupAsset(MongoModel):
    asset_id: str = Field(default_factory=new_id)
    project_id: str
    user_id: str
    file_url: str
    storage_key: str
    original_filename: str
    # Set only for screens that came from a multi-page upload.
    batch_id: str | None = None
    page_number: int | None = None
    format: AssetFormat
    file_size_kb: int
    width: int = 0                           # addition
    height: int = 0                          # addition
    status: AssetStatus = AssetStatus.PENDING
    uploaded_at: datetime = Field(default_factory=utcnow)


class FocusNode(BaseModel):
    x: int
    y: int
    rank: int
    intensity: float


class HeatmapResult(MongoModel):
    result_id: str = Field(default_factory=new_id)
    asset_id: str
    user_id: str
    heatmap_url: str
    saliency_array_url: str
    clarity_score: float
    focus_index: float                       # addition
    clutter_index: float                     # addition
    region_saliency: dict[str, float]        # addition (3x3 grid)
    focus_nodes: list[FocusNode]
    # Longer sequence used only for the animated scanpath. Its first five entries
    # are the same peaks as focus_nodes; existing documents predate this field.
    scanpath_nodes: list[FocusNode] = Field(default_factory=list)
    model_version: str
    inference_time_ms: int
    created_at: datetime = Field(default_factory=utcnow)


class ABComparison(MongoModel):
    comparison_id: str = Field(default_factory=new_id)
    user_id: str
    asset_id_a: str
    asset_id_b: str
    clarity_delta: float
    created_at: datetime = Field(default_factory=utcnow)


class InferenceTask(MongoModel):
    task_id: str = Field(default_factory=new_id)
    asset_id: str
    user_id: str
    status: TaskStatus = TaskStatus.PENDING
    stage: str = "queued"
    error: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    completed_at: datetime | None = None


class SuggestionItem(BaseModel):
    title: str
    detail: str
    severity: str
    based_on: str


class SuggestionDoc(MongoModel):
    suggestion_id: str = Field(default_factory=new_id)
    result_id: str
    user_id: str
    provider: str
    model_name: str
    summary: str
    items: list[SuggestionItem]
    llm_status: LLMStatus
    created_at: datetime = Field(default_factory=utcnow)
