"""API and run-state models shared by the report pipeline."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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


class FollowUpRequest(BaseModel):
    """A refinement question asked against a completed report."""

    message: str = Field(min_length=1, max_length=2_000)
    conversation_id: str | None = None

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_prompt_field(cls, data: object) -> object:
        """Map the legacy ``prompt`` field name onto ``message`` before validation."""

        if isinstance(data, dict) and "message" not in data and "prompt" in data:
            return {**data, "message": data["prompt"]}
        return data

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, message: str) -> str:
        normalized = message.strip()
        if not normalized:
            raise ValueError("message must not be blank")
        return normalized

    @field_validator("conversation_id")
    @classmethod
    def conversation_id_trimmed(cls, value: str | None) -> str | None:
        return value.strip() if value else value


class ScheduleFrequency(StrEnum):
    """Supported recurring-run frequencies."""

    ONCE = "once"
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class ScheduleCreate(BaseModel):
    """A recurring report schedule."""

    topic: str = Field(min_length=1, max_length=500)
    frequency: ScheduleFrequency | None = None
    cron: str | None = None
    enabled: bool = True
    run_id: str | None = None

    @field_validator("topic")
    @classmethod
    def schedule_topic_must_not_be_blank(cls, topic: str) -> str:
        normalized = topic.strip()
        if not normalized:
            raise ValueError("topic must not be blank")
        return normalized

    @field_validator("cron")
    @classmethod
    def schedule_values_are_trimmed(cls, value: str | None) -> str | None:
        return value.strip() if value else value

    @model_validator(mode="after")
    def require_one_schedule_expression(self) -> ScheduleCreate:
        if bool(self.frequency) == bool(self.cron):
            raise ValueError("provide exactly one of frequency or cron")
        if self.cron:
            fields = self.cron.split()
            if len(fields) != 5:
                raise ValueError("cron must contain five fields")
        return self


class Schedule(ScheduleCreate):
    """Persisted recurring schedule state."""

    id: str
    created_at: datetime
    next_run_at: datetime
    last_run_at: datetime | None = None
    last_run_id: str | None = None


class Notification(BaseModel):
    """A stored in-app notification about a report run."""

    id: str
    type: str = "run_completed"
    title: str
    message: str
    read: bool = False
    run_id: str | None = None
    created_at: datetime


class NotificationReadPatch(BaseModel):
    """Patch body for marking a notification read."""

    read: bool


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
    SELF_EVALUATING = "SELF_EVALUATING"
    RESEARCH_ROUND = "RESEARCH_ROUND"
    RENDERING = "RENDERING"
    DONE = "DONE"
    FAILED = "FAILED"


class StageTiming(BaseModel):
    """Monotonic elapsed-time telemetry for one pipeline stage."""

    elapsed_ms: float = Field(ge=0)
    budget_seconds: float | None = Field(default=None, ge=0)
    within_budget: bool | None = None


class ReportRun(BaseModel):
    """Durable snapshot of one report request."""

    model_config = ConfigDict(use_enum_values=True)

    id: str
    topic: str
    prompt: str | None = None
    parent_run_id: str | None = None
    schedule_id: str | None = None
    status: str = "queued"
    stage: Stage = Stage.PLANNING
    sources: list[SourceEntry] = Field(default_factory=list)
    report_md: str | None = None
    created_at: datetime
    error: str | None = None
    outcome: str = "pending"
    message: str | None = None
    partial: bool = False
    stage_timings: dict[str, StageTiming] = Field(default_factory=dict)
    total_elapsed_ms: float = Field(default=0, ge=0)
    budget_status: str = "within_budget"
    search_calls: int = Field(default=0, ge=0)
    max_search_calls: int = Field(default=8, ge=1)
    attempted_sources: int = Field(default=0, ge=0)
    succeeded_sources: int = Field(default=0, ge=0)
    research_rounds: int = Field(default=0, ge=0, le=1)
    gap_reasons: list[str] = Field(default_factory=list)


class RunEvent(BaseModel):
    """One replayable event in a report run's event stream."""

    seq: int = Field(ge=1)
    type: str
    payload: dict[str, object] = Field(default_factory=dict)
    created_at: datetime
