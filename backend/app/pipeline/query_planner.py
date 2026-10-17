"""Fault-tolerant LLM query planning for research topics."""

from __future__ import annotations

import json
import logging
from typing import Any

from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config import Settings
from app.prompts.query_plan import QUERY_PLAN_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class QueryPlan(BaseModel):
    """The deliberately small JSON contract returned by the planner."""

    model_config = ConfigDict(extra="forbid")

    sub_queries: list[str] = Field(min_length=2, max_length=4)

    @field_validator("sub_queries")
    @classmethod
    def validate_queries(cls, queries: list[str]) -> list[str]:
        """Trim queries and reject empty or duplicate entries."""

        normalized = [query.strip() for query in queries]
        if any(not query for query in normalized):
            raise ValueError("sub_queries must contain non-empty strings")
        if len(set(normalized)) != len(normalized):
            raise ValueError("sub_queries must not contain duplicates")
        return normalized


class QueryPlanner:
    """Convert a topic into search queries without blocking the pipeline."""

    def __init__(
        self,
        client: AsyncOpenAI | None,
        model: str,
        *,
        timeout_seconds: float = 60.0,
    ) -> None:
        self._client = client
        self._model = model
        self._timeout_seconds = timeout_seconds

    @classmethod
    def from_settings(cls, settings: Settings) -> QueryPlanner:
        """Build a planner, leaving it disabled when no LLM key is configured."""

        client = None
        if settings.llm_configured and not settings.mock_mode:
            client = AsyncOpenAI(
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url,
                timeout=60.0,
                max_retries=0,
            )
        return cls(client, settings.llm_model)

    async def plan(self, topic: str) -> list[str]:
        """Return 2–4 focused queries, or ``[topic]`` for any planner failure."""

        fallback = [topic]
        if self._client is None or not topic.strip():
            return fallback

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": QUERY_PLAN_SYSTEM_PROMPT},
                    {"role": "user", "content": topic},
                ],
                response_format={"type": "json_object"},
                timeout=self._timeout_seconds,
            )
            content = self._response_content(response)
            payload = json.loads(content)
            return QueryPlan.model_validate(payload).sub_queries
        except Exception as exc:
            logger.warning(
                "Query planning failed (%s); using the original topic",
                type(exc).__name__,
            )
            return fallback

    @staticmethod
    def _response_content(response: Any) -> str:
        """Extract content while treating malformed SDK responses as failures."""

        choices = getattr(response, "choices", None)
        if not choices:
            raise ValueError("LLM returned no choices")
        content = getattr(getattr(choices[0], "message", None), "content", None)
        if not isinstance(content, str) or not content.strip():
            raise ValueError("LLM returned empty content")
        return content
