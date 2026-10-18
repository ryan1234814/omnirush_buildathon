"""Tests for the Phase 2 search providers."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.pipeline.search import MockSearch, SearchConfigurationError, SearchError, TavilySearch


class FakeTavilyClient:
    def __init__(self, response: object) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    async def search(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return self.response


class RateLimitError(RuntimeError):
    status_code = 429


@pytest.mark.asyncio
async def test_tavily_search_forwards_options_and_normalizes_results() -> None:
    client = FakeTavilyClient(
        {
            "answer": "summary",
            "results": [
                {
                    "title": "A source",
                    "url": "https://example.com/a",
                    "content": "Useful context",
                    "score": 0.9,
                    "published_date": "2026-01-01",
                },
                {"title": "missing URL"},
            ],
        }
    )
    provider = TavilySearch("test-key", client=client)  # type: ignore[arg-type]

    results = await provider.search("a topic", 2)

    assert client.calls == [
        {
            "query": "a topic",
            "max_results": 2,
            "include_answer": True,
            "search_depth": "advanced",
        }
    ]
    assert results[0].title == "A source"
    assert results[0].query == "a topic"
    assert results[0].score == 0.9


@pytest.mark.asyncio
async def test_tavily_search_rejects_malformed_response() -> None:
    client = FakeTavilyClient({"answer": "no results key"})
    provider = TavilySearch("test-key", client=client)  # type: ignore[arg-type]

    with pytest.raises(SearchError, match="invalid search response"):
        await provider.search("topic", 3)


@pytest.mark.asyncio
async def test_tavily_search_retries_a_rate_limit_once_with_bounded_backoff() -> None:
    client = FakeTavilyClient(
        {
            "results": [
                {"title": "Recovered", "url": "https://example.com/recovered"},
            ]
        }
    )
    original_search = client.search
    attempts = 0

    async def rate_limited_once(**kwargs: object) -> object:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RateLimitError()
        return await original_search(**kwargs)

    client.search = rate_limited_once  # type: ignore[method-assign]
    provider = TavilySearch("test-key", client=client, retry_backoff_seconds=0.001)  # type: ignore[arg-type]

    results = await provider.search("topic", 1)

    assert len(results) == 1
    assert attempts == 2


@pytest.mark.asyncio
async def test_tavily_search_stops_after_one_rate_limit_retry() -> None:
    client = FakeTavilyClient({"results": []})
    attempts = 0

    async def always_rate_limited(**kwargs: object) -> object:
        nonlocal attempts
        attempts += 1
        raise RateLimitError()

    client.search = always_rate_limited  # type: ignore[method-assign]
    provider = TavilySearch("test-key", client=client, retry_backoff_seconds=0.001)  # type: ignore[arg-type]

    with pytest.raises(SearchError):
        await provider.search("topic", 1)

    assert attempts == 2


def test_tavily_search_requires_a_key_without_injected_client() -> None:
    with pytest.raises(SearchConfigurationError, match="TAVILY_API_KEY"):
        TavilySearch(None)


@pytest.mark.asyncio
async def test_mock_search_is_deterministic_and_respects_limit(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture.json"
    fixture.write_text(
        '{"results": [{"title": "One", "url": "https://one.test"}, '
        '{"title": "Two", "url": "https://two.test"}]}',
        encoding="utf-8",
    )
    provider = MockSearch(fixture)

    results = await provider.search("chosen topic", 1)

    assert len(results) == 1
    assert results[0].title == "One"
    assert results[0].query == "chosen topic"


@pytest.mark.asyncio
async def test_default_mock_search_uses_six_saved_pages_and_special_topics() -> None:
    provider = MockSearch()

    results = await provider.search("quantum computing 2026", 8)
    zero_results = await provider.search("zero results drill", 8)
    dead_results = await provider.search("dead source drill", 8)

    assert len(results) == 6
    assert all("2026" in result.url for result in results)
    assert all(len(result.content) > 200 for result in results)
    assert zero_results == []
    assert len(dead_results) == 1


def test_mock_search_rejects_missing_fixture(tmp_path: Path) -> None:
    with pytest.raises(SearchConfigurationError, match="not found"):
        MockSearch(tmp_path / "missing.json")
