"""API and run-state models shared by the report pipeline."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TopicRequest(BaseModel):
    """Validated topic submitted by an API client."""

    topic: str = Field(min_length=1, max_length=500)

    @field_validator("topic")
    @classmethod
    def topic_must_not_be_blank(cls, topic: str) -> str:
        """Reject whitespace-only topics and normalize surrounding whitespace."""

        normalized = topic.strip()
        if not normalized:
            raise ValueError("topic must not be blank")
        return normalized


class SourceEntry(BaseModel):
    """Citation-safe source data exposed to synthesis and API clients."""

    id: int = Field(ge=1)
    url: str
    title: str
    excerpt: str


class SourceRegistry(BaseModel):
    """Ordered, bounded source context for a report."""

    entries: list[SourceEntry] = Field(default_factory=list)
    context_token_estimate: int = Field(default=0, ge=0)


class Stage(StrEnum):
    """Observable pipeline stages."""

    PLANNING = "PLANNING"
    SEARCHING = "SEARCHING"
    EXTRACTING = "EXTRACTING"
    RANKING = "RANKING"
    SYNTHESIZING = "SYNTHESIZING"
    RENDERING = "RENDERING"
    DONE = "DONE"
    FAILED = "FAILED"


class ReportRun(BaseModel):
    """Durable snapshot of one report request."""

    model_config = ConfigDict(use_enum_values=True)

    id: str
    topic: str
    status: str = "queued"
    stage: Stage = Stage.PLANNING
    sources: list[SourceEntry] = Field(default_factory=list)
    report_md: str | None = None
    created_at: datetime
    error: str | None = None


class RunEvent(BaseModel):
    """One replayable event in a report run's event stream."""

    seq: int = Field(ge=1)
    type: str
    payload: dict[str, object] = Field(default_factory=dict)
    created_at: datetime
