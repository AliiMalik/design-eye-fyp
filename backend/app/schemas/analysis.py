"""Project, asset, result, comparison, and suggestion schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


# --- projects ------------------------------------------------------------
class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=1000)


class ProjectUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=1000)


class ProjectResponse(BaseModel):
    project_id: str
    user_id: str
    title: str
    description: str | None = None
    created_at: datetime
    updated_at: datetime
    asset_count: int = 0
    avg_clarity_score: float | None = None


class ProjectListResponse(BaseModel):
    projects: list[ProjectResponse]
    total_count: int
    page: int
    limit: int


# --- assets --------------------------------------------------------------
class AssetResponse(BaseModel):
    asset_id: str
    project_id: str
    user_id: str
    file_url: str
    original_filename: str
    format: str
    file_size_kb: int
    width: int = 0
    height: int = 0
    status: str
    uploaded_at: datetime


class UploadResponse(BaseModel):
    """202 Accepted payload for POST /upload."""

    asset_id: str
    task_id: str
    status: str = "pending"


class ProjectDetailResponse(BaseModel):
    project: ProjectResponse
    assets: list[AssetResponse]


# --- results -------------------------------------------------------------
class FocusNodeSchema(BaseModel):
    x: int
    y: int
    rank: int
    intensity: float


class ScanpathStep(BaseModel):
    rank: int
    x: int
    y: int
    intensity: float
    start_ms: int
    dwell_ms: int
    end_ms: int


class ResultResponse(BaseModel):
    result_id: str
    asset_id: str
    heatmap_url: str
    saliency_array_url: str
    mockup_url: str
    clarity_score: float
    focus_index: float
    clutter_index: float
    region_saliency: dict[str, float]
    focus_nodes: list[FocusNodeSchema]
    scanpath: list[ScanpathStep] = Field(default_factory=list)
    scanpath_total_ms: int = 0
    model_version: str
    inference_time_ms: int
    created_at: datetime
    image_width: int = 0
    image_height: int = 0
    original_filename: str = ""
    project_id: str = ""


class StatusResponse(BaseModel):
    """GET /status/{task_id} - drives the frontend progress narrative."""

    task_id: str
    asset_id: str
    status: str
    stage: str
    error: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
    result_url: str | None = None
    clarity_score: float | None = None
    focus_nodes: list[FocusNodeSchema] | None = None


class RerunResponse(BaseModel):
    new_task_id: str
    status: str = "pending"


class ResultListItem(BaseModel):
    asset_id: str
    project_id: str
    original_filename: str
    status: str
    uploaded_at: datetime
    clarity_score: float | None = None
    heatmap_url: str | None = None
    mockup_url: str | None = None
    width: int = 0
    height: int = 0


class ResultListResponse(BaseModel):
    results: list[ResultListItem]
    total_count: int
    page: int
    limit: int


# --- comparison ----------------------------------------------------------
class CompareRequest(BaseModel):
    asset_id_a: str
    asset_id_b: str


class ComparisonSide(BaseModel):
    asset_id: str
    original_filename: str
    mockup_url: str
    heatmap_url: str
    clarity_score: float
    focus_index: float
    clutter_index: float
    focus_nodes: list[FocusNodeSchema]
    region_saliency: dict[str, float]
    width: int = 0
    height: int = 0


class ComparisonResponse(BaseModel):
    comparison_id: str
    clarity_delta: float
    winner: str
    design_a: ComparisonSide
    design_b: ComparisonSide
    created_at: datetime


class ComparisonListItem(BaseModel):
    comparison_id: str
    asset_id_a: str
    asset_id_b: str
    clarity_delta: float
    created_at: datetime


class ComparisonListResponse(BaseModel):
    comparisons: list[ComparisonListItem]
    total_count: int
    page: int
    limit: int


# --- suggestions ---------------------------------------------------------
class SuggestionItemSchema(BaseModel):
    title: str
    detail: str
    severity: str
    based_on: str


class SuggestionsRequest(BaseModel):
    user_context: str | None = Field(default=None, max_length=1000)
    regenerate: bool = False


class SuggestionsResponse(BaseModel):
    result_id: str | None = None
    summary: str = ""
    suggestions: list[SuggestionItemSchema] = Field(default_factory=list)
    llm_status: str
    provider: str = ""
    model_name: str = ""
    created_at: datetime | None = None


# --- dashboard -----------------------------------------------------------
class ClarityTrendPoint(BaseModel):
    date: datetime
    clarity_score: float
    asset_id: str
    original_filename: str


class DashboardStats(BaseModel):
    total_projects: int
    total_analyses: int
    avg_clarity_score: float
    projects_this_month: int
    clarity_trend: list[ClarityTrendPoint] = Field(default_factory=list)
    recent_assets: list[ResultListItem] = Field(default_factory=list)
