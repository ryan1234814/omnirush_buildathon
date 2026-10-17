"""Tests for concurrent extraction and graceful source failures."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.pipeline.extract import fetch_sources
from app.pipeline.search import SearchResult


@dataclass
class FakeResponse:
    text: str

    def raise_for_status(self) -> None:
        return None


class FakeHttpClient:
    def __init__(self, html: str) -> None:
        self.html = html
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def get(self, url: str, **kwargs: object) -> FakeResponse:
        self.calls.append((url, kwargs))
        return FakeResponse(self.html)


class FakeTavilyClient:
    async def extract(self, urls: list[str]) -> dict[str, object]:
        if "tavily" in urls[0]:
            return {"results": [{"raw_content": "Tavily extracted article text."}]}
        return {"results": []}


def result(url: str, content: str = "") -> SearchResult:
    return SearchResult(
        title="Fixture title",
        url=url,
        content=content,
        score=0.8,
    )


@pytest.mark.asyncio
async def test_fetch_sources_uses_tavily_then_http_fallback() -> None:
    html = (
        "<html><body><article><h1>Fallback title</h1><p>"
        + ("Fallback article text with enough detail for extraction. " * 20)
        + "</p></article></body></html>"
    )
    http_client = FakeHttpClient(html)

    sources = await fetch_sources(
        [result("https://tavily.test/source"), result("https://fallback.test/source")],
        tavily_client=FakeTavilyClient(),
        http_client=http_client,  # type: ignore[arg-type]
    )

    assert len(sources) == 2
    assert sources[0].extraction_method == "tavily"
    assert sources[1].extraction_method == "http"
    assert http_client.calls[0][1]["headers"]
    assert "Mobile" in str(http_client.calls[0][1]["headers"])


@pytest.mark.asyncio
async def test_mock_mode_uses_fixture_content_without_http() -> None:
    sources = await fetch_sources(
        [result("https://fixture.test/source", "Offline fixture content.")],
        mock_mode=True,
    )

    assert len(sources) == 1
    assert sources[0].content == "Offline fixture content."
    assert sources[0].extraction_method == "mock"


@pytest.mark.asyncio
async def test_empty_or_failed_sources_are_skipped() -> None:
    sources = await fetch_sources(
        [result("https://fixture.test/empty")],
        mock_mode=True,
    )

    assert sources == []
