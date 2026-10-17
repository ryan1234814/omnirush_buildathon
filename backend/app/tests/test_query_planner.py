"""Tests for fault-tolerant LLM query planning."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.pipeline.query_planner import QueryPlanner


class FakeCompletions:
    def __init__(self, responses: list[object]) -> None:
        self.responses = responses
        self.calls: list[dict[str, object]] = []

    async def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return self.responses[0]


def fake_client(content: str | None, *, choices: bool = True) -> tuple[object, FakeCompletions]:
    completions = FakeCompletions(
        [
            SimpleNamespace(
                choices=(
                    [SimpleNamespace(message=SimpleNamespace(content=content))] if choices else []
                )
            )
        ]
    )
    return SimpleNamespace(chat=SimpleNamespace(completions=completions)), completions


@pytest.mark.asyncio
async def test_planner_validates_and_normalizes_json() -> None:
    client, completions = fake_client('{"sub_queries": ["  first angle ", "second angle"]}')

    queries = await QueryPlanner(client, "test-model").plan("a topic")  # type: ignore[arg-type]

    assert queries == ["first angle", "second angle"]
    assert completions.calls[0]["response_format"] == {"type": "json_object"}
    assert completions.calls[0]["model"] == "test-model"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content",
    [
        "not json",
        '{"sub_queries": ["only one"]}',
        '{"sub_queries": ["same", "same"]}',
        '{"sub_queries": ["a", 2]}',
        '{"sub_queries": ["a", "b"], "extra": true}',
    ],
)
async def test_planner_falls_back_for_any_invalid_payload(content: str) -> None:
    client, _ = fake_client(content)

    assert await QueryPlanner(client, "test-model").plan("original topic") == ["original topic"]  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_planner_falls_back_for_empty_response() -> None:
    client, _ = fake_client(None, choices=False)

    assert await QueryPlanner(client, "test-model").plan("original topic") == ["original topic"]  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_planner_without_client_does_not_call_an_llm() -> None:
    assert await QueryPlanner(None, "test-model").plan("original topic") == ["original topic"]
