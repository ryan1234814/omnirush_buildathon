"""Search provider abstractions and the Phase 2 provider implementations."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import httpx
from tavily import AsyncTavilyClient

from app.mock.corpus import MockPage, load_corpus

logger = logging.getLogger(__name__)


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

    def remaining(self) -> int:
        """Return how many attempts are left before the shared cap is full."""

        return max(0, self.max_calls - self.calls)


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


class FallbackSearch:
    """Use a secondary provider whenever the primary search fails or errors.

    The primary attempt is charged against the shared call budget (so paid API
    usage stays capped). The fallback is intended for free scraping, so it is
    still allowed to answer once the primary budget is exhausted.
    """

    def __init__(
        self,
        primary: SearchProvider,
        fallback: SearchProvider,
        *,
        call_budget: SearchCallBudget | None = None,
        fallback_on_empty: bool = False,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._call_budget = call_budget
        self._fallback_on_empty = fallback_on_empty

    async def search(self, query: str, max_results: int) -> list[SearchResult]:
        """Return primary results, or Scrapling results when the primary fails."""

        if not query.strip() or max_results < 1:
            return []
        if self._call_budget is not None and not await self._call_budget.reserve():
            logger.info("Primary search budget exhausted; using fallback for %r", query)
            return await self._fallback.search(query, max_results)
        try:
            results = await self._primary.search(query, max_results)
        except SearchError as exc:
            logger.warning(
                "Primary search failed (%s); using fallback for %r", type(exc).__name__, query
            )
            return await self._fallback.search(query, max_results)
        if results or not self._fallback_on_empty:
            return results
        return await self._fallback.search(query, max_results)


TranscriptLoader = Callable[[str], Awaitable[str]]


class YouTubeTranscriptProvider:
    """Search YouTube and attach transcripts through an async-swappable loader.

    The loader seam keeps tests and deployments that use a different transcript service
    independent of the Google API. The optional default loader uses
    ``youtube_transcript_api`` when it is installed; missing credentials or that optional
    package are reported as provider errors rather than crashing application startup.
    """

    def __init__(
        self,
        api_key: str | None,
        *,
        transcript_loader: TranscriptLoader | None = None,
        timeout_seconds: float = 10.0,
        call_budget: SearchCallBudget | None = None,
    ) -> None:
        if not api_key:
            raise SearchConfigurationError(
                "YouTube search is not configured: YOUTUBE_API_KEY is missing"
            )
        self._api_key = api_key
        self._transcript_loader = transcript_loader or self._load_transcript
        self._timeout_seconds = timeout_seconds
        self._call_budget = call_budget

    async def _load_transcript(self, video_id: str) -> str:
        """Load a transcript without making the synchronous library block the loop."""

        try:
            from youtube_transcript_api import YouTubeTranscriptApi
        except ImportError as exc:
            raise SearchError(
                "YouTube transcripts require the optional youtube-transcript-api package"
            ) from exc

        def read_transcript() -> str:
            transcript = YouTubeTranscriptApi.get_transcript(video_id)
            return " ".join(str(item.get("text", "")) for item in transcript).strip()

        return await asyncio.to_thread(read_transcript)

    async def search(self, query: str, max_results: int) -> list[SearchResult]:
        """Return transcript-backed YouTube videos for a query."""

        if not query.strip() or max_results < 1:
            return []
        if self._call_budget is not None and not await self._call_budget.reserve():
            return []
        params = {
            "part": "snippet",
            "q": query,
            "type": "video",
            "maxResults": min(max_results, 50),
            "key": self._api_key,
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.get(
                    "https://www.googleapis.com/youtube/v3/search", params=params
                )
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise SearchError("YouTube search failed; check the API key and status") from exc
        items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            raise SearchError("YouTube returned an invalid search response")
        results: list[SearchResult] = []
        for item in items:
            video_id = ((item.get("id") or {}).get("videoId") if isinstance(item, dict) else None)
            snippet = item.get("snippet", {}) if isinstance(item, dict) else {}
            if not video_id or not isinstance(snippet, dict):
                continue
            try:
                transcript = await self._transcript_loader(str(video_id))
            except SearchError:
                raise
            except Exception as exc:
                raise SearchError("YouTube transcript ingestion failed") from exc
            if not transcript.strip():
                continue
            results.append(
                SearchResult(
                    title=_as_text(snippet.get("title"), f"YouTube video {video_id}"),
                    url=f"https://www.youtube.com/watch?v={video_id}",
                    content=transcript,
                    score=1.0 - len(results) / max(1, len(items)),
                    published_date=_as_text(snippet.get("publishedAt")) or None,
                    query=query,
                )
            )
        return results[:max_results]


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
            # Corpus pages answer any query built around the saved topic, which also
            # covers second research-round queries that extend the original topic.
            if not normalized_query.startswith(
                ("quantum", "gap drill", "research gap", "synthesis timeout")
            ):
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
