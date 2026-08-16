"""Shared response schemas."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class MessageResponse(BaseModel):
    message: str


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    db: bool
    redis: bool
    version: str
    dev_mode: bool
    model_info: dict = Field(default_factory=dict)


class Paginated(BaseModel, Generic[T]):
    items: list[T]
    total_count: int
    page: int
    limit: int

    @property
    def pages(self) -> int:
        return max(1, -(-self.total_count // self.limit))
