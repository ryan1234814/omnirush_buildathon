"""Tests for the Scrapling fallback that backs up the Tavily search provider."""

from __future__ import annotations

import pytest
from scrapling.parser import Adaptor

from app.pipeline.scrapling_search import ScraplingSearch, fetch_page_html
from app.pipeline.search import (
    FallbackSearch,
    SearchCallBudget,
    SearchError,
    SearchResult,
)

RESULTS_HTML = """
<html><body>
  <div class="result">
    <a class="result__a" href="https://example.com/first">First result</a>
    <a class="result__snippet">A useful first snippet.</a>
  </div>
  <div class="result">
    <a class="result__a"
       href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fsecond">Second</a>
    <a class="result__snippet">A useful second snippet.</a>
  </div>
  <div class="result">
    <a class="result__a" href="https://example.com/third">Third result</a>
    <a class="result__snippet">A useful third snippet.</a>
  </div>
</body></html>
"""

EMPTY_HTML = "<html><body><p>No results here.</p></body></html>"


class FakePage:
    """A minimal stand-in for a Scrapling response."""

    def __init__(self, html: str, status: int = 200) -> None:
        self._adaptor = Adaptor(html, url="https://html.duckduckgo.com/html/")
        self.status = status

    def css(self, selector: str) -> object:
        return self._adaptor.css(selector)


class RecordingFallback:
    def __init__(self, results: list[SearchResult]) -> None:
        self.results = results
        self.calls = 0

    async def search(self, query: str, max_results: int) -> list[SearchResult]:
        self.calls += 1
        return self.results[:max_results]


class FailingPrimary:
    async def search(self, query: str, max_results: int) -> list[SearchResult]:
        raise SearchError("primary exploded")


class WorkingPrimary:
    def __init__(self, results: list[SearchResult]) -> None:
        self.results = results
        self.calls = 0

    async def search(self, query: str, max_results: int) -> list[SearchResult]:
        self.calls += 1
        return self.results[:max_results]


def _result(url: str = "https://fallback.test/a") -> SearchResult:
    return SearchResult(title="Fallback", url=url, content="Fallback content", score=0.7)


@pytest.mark.asyncio
async def test_scrapling_search_parses_duckduckgo_results() -> None:
    provider = ScraplingSearch(fetcher=lambda query, timeout: FakePage(RESULTS_HTML))

    results = await provider.search("quantum computing", 2)

    assert [result.url for result in results] == [
        "https://example.com/first",
        "https://example.com/second",
    ]
    assert results[0].title == "First result"
    assert results[0].content == "A useful first snippet."
    assert results[1].url == "https://example.com/second"
    assert all(result.query == "quantum computing" for result in results)


@pytest.mark.asyncio
async def test_scrapling_search_raises_when_no_results() -> None:
    provider = ScraplingSearch(fetcher=lambda query, timeout: FakePage(EMPTY_HTML))

    with pytest.raises(SearchError, match="no parseable results"):
        await provider.search("nothing", 5)


@pytest.mark.asyncio
async def test_scrapling_search_wraps_fetcher_failures() -> None:
    def boom(query: str, timeout: float) -> object:
        raise RuntimeError("network down")

    provider = ScraplingSearch(fetcher=boom)

    with pytest.raises(SearchError, match="Scrapling search failed"):
        await provider.search("topic", 3)


@pytest.mark.asyncio
async def test_scrapling_search_rejects_http_error_status() -> None:
    provider = ScraplingSearch(fetcher=lambda query, timeout: FakePage(RESULTS_HTML, status=503))

    with pytest.raises(SearchError, match="HTTP 503"):
        await provider.search("topic", 3)


@pytest.mark.asyncio
async def test_fetch_page_html_returns_empty_on_failure() -> None:
    def boom(url: str, timeout: float) -> object:
        raise RuntimeError("blocked")

    assert await fetch_page_html("https://example.com", fetcher=boom) == ""


@pytest.mark.asyncio
async def test_fallback_search_uses_fallback_when_primary_fails() -> None:
    fallback = RecordingFallback([_result()])
    provider = FallbackSearch(FailingPrimary(), fallback)

    results = await provider.search("topic", 5)

    assert results == [_result()]
    assert fallback.calls == 1


@pytest.mark.asyncio
async def test_fallback_search_prefers_primary_results() -> None:
    primary_result = SearchResult(title="Primary", url="https://primary.test/a", content="ok")
    primary = WorkingPrimary([primary_result])
    fallback = RecordingFallback([_result()])
    provider = FallbackSearch(primary, fallback)

    results = await provider.search("topic", 5)

    assert results == [primary_result]
    assert primary.calls == 1
    assert fallback.calls == 0


@pytest.mark.asyncio
async def test_fallback_search_runs_when_budget_is_exhausted() -> None:
    primary = WorkingPrimary([_result("https://primary.test/a")])
    fallback = RecordingFallback([_result("https://fallback.test/b")])
    provider = FallbackSearch(primary, fallback, call_budget=SearchCallBudget(0))

    results = await provider.search("topic", 5)

    assert primary.calls == 0
    assert fallback.calls == 1
    assert results[0].url == "https://fallback.test/b"
