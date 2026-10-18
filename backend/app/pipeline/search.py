"""Search provider abstractions and the Phase 2 provider implementations."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from tavily import AsyncTavilyClient

from app.mock.corpus import MockPage, load_corpus


class SearchError(RuntimeError):
    """A search provider could not complete a request."""


class SearchConfigurationError(SearchError):
    """A provider is not configured correctly."""


class SearchCallBudget:
    """Atomically cap provider attempts shared by all planned queries in a run."""

    def __init__(self, max_calls: int) -> None:
        self.max_calls = max(0, max_calls)
        self.calls = 0
        self._lock = asyncio.Lock()

    async def reserve(self) -> bool:
        """Reserve one provider attempt, returning false after the cap is full."""

        async with self._lock:
            if self.calls >= self.max_calls:
                return False
            self.calls += 1
            return True


@dataclass(frozen=True, slots=True)
class SearchResult:
    """A provider-independent search result."""

    title: str
    url: str
    content: str
    score: float = 0.0
    published_date: str | None = None
    query: str | None = None


class SearchProvider(Protocol):
    """Async interface shared by real and offline search providers."""

    async def search(self, query: str, max_results: int) -> list[SearchResult]:
        """Return at most ``max_results`` results for ``query``."""


def _as_text(value: Any, default: str = "") -> str:
    """Convert an optional provider value to trimmed text."""

    return value.strip() if isinstance(value, str) else default


def _as_score(value: Any) -> float:
    """Convert a provider score to a safe float."""

    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _result_from_mapping(item: Any, query: str) -> SearchResult | None:
    """Normalize one provider record, skipping records without a URL."""

    if not isinstance(item, dict):
        return None
    url = _as_text(item.get("url"))
    if not url:
        return None
    title = _as_text(item.get("title"), url)
    return SearchResult(
        title=title,
        url=url,
        content=_as_text(item.get("content")),
        score=_as_score(item.get("score")),
        published_date=_as_text(item.get("published_date")) or None,
        query=query,
    )


class TavilySearch:
    """Search Tavily through its async SDK with an application timeout."""

    def __init__(
        self,
        api_key: str | None,
        *,
        client: AsyncTavilyClient | None = None,
        timeout_seconds: float = 10.0,
        retry_backoff_seconds: float = 0.25,
        call_budget: SearchCallBudget | None = None,
    ) -> None:
        if not api_key and client is None:
            raise SearchConfigurationError(
                "Tavily search is not configured: TAVILY_API_KEY is missing"
            )
        self._client = client or AsyncTavilyClient(api_key=api_key)
        self._timeout_seconds = timeout_seconds
        self._retry_backoff_seconds = min(max(0.0, retry_backoff_seconds), 5.0)
        self._call_budget = call_budget

    async def search(self, query: str, max_results: int) -> list[SearchResult]:
        """Run an advanced Tavily search and normalize its result records."""

        if not query.strip():
            return []
        if max_results < 1:
            return []
        response = None
        for attempt in range(2):
            if self._call_budget is not None and not await self._call_budget.reserve():
                return []
            try:
                response = await asyncio.wait_for(
                    self._client.search(
                        query=query,
                        max_results=max_results,
                        include_answer=True,
                        search_depth="advanced",
                    ),
                    timeout=self._timeout_seconds,
                )
                break
            except TimeoutError as exc:
                raise SearchError("Tavily search timed out") from exc
            except Exception as exc:
                status_code = getattr(exc, "status_code", None) or getattr(
                    getattr(exc, "response", None), "status_code", None
                )
                if status_code == 429 and attempt == 0:
                    await asyncio.sleep(self._retry_backoff_seconds)
                    continue
                raise SearchError(
                    "Tavily search failed; check the API key and service status"
                ) from exc

        if response is None:
            raise SearchError("Tavily search did not return a response")

        if not isinstance(response, dict) or not isinstance(response.get("results"), list):
            raise SearchError("Tavily returned an invalid search response")
        return [
            result
            for item in response["results"]
            if (result := _result_from_mapping(item, query)) is not None
        ][:max_results]


class MockSearch:
    """Deterministic search provider backed by saved local pages."""

    def __init__(
        self,
        fixture_path: str | Path | None = None,
        *,
        call_budget: SearchCallBudget | None = None,
    ) -> None:
        self._call_budget = call_budget
        self._pages: list[MockPage] = []
        path = Path(fixture_path) if fixture_path else None
        if path is None:
            try:
                self._pages = load_corpus()
            except ValueError as exc:
                raise SearchConfigurationError(str(exc)) from exc
            self._results = []
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise SearchConfigurationError(f"Mock search fixture not found: {path}") from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise SearchConfigurationError(f"Mock search fixture is unreadable: {path}") from exc

        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            raise SearchConfigurationError("Mock search fixture must contain a results array")
        self._results = [
            result
            for item in payload["results"]
            if (result := _result_from_mapping(item, "mock")) is not None
        ]

    async def search(self, query: str, max_results: int) -> list[SearchResult]:
        """Return fixture results in a stable order without network access."""

        if max_results < 1 or not query.strip():
            return []
        if self._call_budget is not None and not await self._call_budget.reserve():
            return []
        normalized_query = " ".join(query.casefold().split())
        if normalized_query in {"search failure", "search failure drill"}:
            raise SearchError("mock search failure drill")
        if normalized_query in {"zero results", "zero results drill", "no sources"}:
            return []
        if normalized_query in {"dead source", "dead source drill"}:
            return [
                SearchResult(
                    title="Deliberately unavailable mock source",
                    url="https://offline.mock/quantum-computing-2026/dead-source",
                    content="",
                    score=0.99,
                    query=query,
                )
            ][:max_results]
        if self._pages:
            if normalized_query not in {
                "quantum computing 2026",
                "quantum computing",
                "synthesis timeout drill",
            }:
                return []
            return [
                SearchResult(
                    title=page.title,
                    url=page.url,
                    content=page.text,
                    score=page.score,
                    published_date=page.published_date,
                    query=query,
                )
                for page in self._pages[:max_results]
            ]
        return [
            SearchResult(
                title=result.title,
                url=result.url,
                content=result.content,
                score=result.score,
                published_date=result.published_date,
                query=query,
            )
            for result in self._results[:max_results]
        ]
