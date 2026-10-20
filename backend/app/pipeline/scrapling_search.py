"""Scrapling-backed web search and page fetch used when Tavily is unavailable.

The module is deliberately defensive: the Scrapling import happens lazily so a
missing or broken Scrapling installation degrades to a clean ``SearchError``
(or an empty fetch) instead of crashing application startup.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from app.pipeline.search import SearchCallBudget, SearchError, SearchResult

logger = logging.getLogger(__name__)

DUCKDUCKGO_HTML_ENDPOINT = "https://html.duckduckgo.com/html/"
DEFAULT_TIMEOUT_SECONDS = 15.0

PageFetcher = Callable[[str, float], Any]
SearchFetcher = Callable[[str, float], Any]


def _import_scrapling_fetcher() -> Any:
    """Import Scrapling's static fetcher lazily and report a clean error."""

    try:
        from scrapling.fetchers import Fetcher
    except Exception as exc:  # pragma: no cover - depends on the local install
        raise SearchError("Scrapling is not available for the search fallback") from exc
    return Fetcher


def _default_search_fetcher(query: str, timeout: float) -> Any:
    """Fetch DuckDuckGo's HTML results page through Scrapling."""

    fetcher = _import_scrapling_fetcher()
    return fetcher.post(DUCKDUCKGO_HTML_ENDPOINT, data={"q": query}, timeout=timeout)


def _default_page_fetcher(url: str, timeout: float) -> Any:
    """Fetch a single page through Scrapling's static fetcher."""

    fetcher = _import_scrapling_fetcher()
    return fetcher.get(url, timeout=timeout)


def _text(value: Any) -> str:
    """Normalize a Scrapling text handler into collapsed text."""

    if value is None:
        return ""
    return " ".join(str(value).split())


def _resolve_href(href: str) -> str:
    """Resolve DuckDuckGo redirect links into their destination URL."""

    candidate = (href or "").strip()
    if not candidate:
        return ""
    if candidate.startswith("//"):
        candidate = f"https:{candidate}"
    if "uddg=" in candidate:
        query = parse_qs(urlparse(candidate).query).get("uddg")
        if query:
            return unquote(query[0])
    return candidate


class ScraplingSearch:
    """Search the public web with Scrapling when the primary provider fails.

    Results are read from DuckDuckGo's HTML endpoint and normalized into the
    same ``SearchResult`` shape as the API-backed providers so the rest of the
    pipeline is unaware of the fallback.
    """

    def __init__(
        self,
        *,
        fetcher: SearchFetcher | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        call_budget: SearchCallBudget | None = None,
    ) -> None:
        self._fetcher = fetcher or _default_search_fetcher
        self._timeout_seconds = max(1.0, timeout_seconds)
        self._call_budget = call_budget

    async def search(self, query: str, max_results: int) -> list[SearchResult]:
        """Return up to ``max_results`` scraped results for ``query``."""

        if not query.strip() or max_results < 1:
            return []
        if self._call_budget is not None and not await self._call_budget.reserve():
            return []
        try:
            page = await asyncio.wait_for(
                asyncio.to_thread(self._fetcher, query, self._timeout_seconds),
                timeout=self._timeout_seconds + 5.0,
            )
        except TimeoutError as exc:
            raise SearchError("Scrapling search timed out") from exc
        except SearchError:
            raise
        except Exception as exc:
            raise SearchError("Scrapling search failed") from exc
        return self._parse(page, query, max_results)

    def _parse(self, page: Any, query: str, max_results: int) -> list[SearchResult]:
        """Normalize a DuckDuckGo HTML page into search results."""

        status = getattr(page, "status", None)
        if isinstance(status, int) and status >= 400:
            raise SearchError(f"Scrapling search returned HTTP {status}")
        try:
            nodes = page.css(".result")
        except Exception as exc:
            raise SearchError("Scrapling returned an unreadable page") from exc
        results: list[SearchResult] = []
        for index, node in enumerate(nodes or []):
            if len(results) >= max_results:
                break
            try:
                links = node.css("a.result__a")
            except Exception:
                continue
            if not links:
                continue
            url = _resolve_href(str(links[0].attrib.get("href", "")))
            if not url.startswith("http"):
                continue
            snippets = node.css(".result__snippet")
            results.append(
                SearchResult(
                    title=_text(getattr(links[0], "text", "")) or url,
                    url=url,
                    content=_text(getattr(snippets[0], "text", "")) if snippets else "",
                    score=max(0.0, 1.0 - index * 0.05),
                    query=query,
                )
            )
        if not results:
            raise SearchError("Scrapling search returned no parseable results")
        return results


async def fetch_page_html(
    url: str,
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    fetcher: PageFetcher | None = None,
) -> str:
    """Fetch a page's HTML with Scrapling, returning ``""`` on any failure."""

    fetch = fetcher or _default_page_fetcher
    try:
        page = await asyncio.wait_for(
            asyncio.to_thread(fetch, url, max(1.0, timeout_seconds)),
            timeout=max(1.0, timeout_seconds) + 5.0,
        )
    except Exception as exc:
        logger.warning("Scrapling fetch failed (%s): %s", type(exc).__name__, url)
        return ""
    return str(getattr(page, "html_content", "") or "")
