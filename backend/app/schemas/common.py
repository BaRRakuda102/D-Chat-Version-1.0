from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MessageResponse(BaseModel):
    message: str


class HealthDependencyStatus(BaseModel):
    status: str
    latency_ms: float | None = None


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    timestamp: datetime
    database: HealthDependencyStatus
    redis: HealthDependencyStatus


class PaginationParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skip: int = 0
    limit: int = 100
