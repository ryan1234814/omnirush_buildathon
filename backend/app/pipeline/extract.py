"""Concurrent source extraction with Tavily and a local HTTP fallback."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import httpx
import trafilatura
from tavily import AsyncTavilyClient

from app.mock.corpus import page_for_url
from app.pipeline.scrapling_search import fetch_page_html
from app.pipeline.search import SearchResult

logger = logging.getLogger(__name__)

MOBILE_USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 13; Mobile) AppleWebKit/537.36 Chrome/120.0 Mobile Safari/537.36"
)


@dataclass(frozen=True, slots=True)
class Source:
    """Extracted source content and metadata used by the ranker."""

    title: str
    url: str
    content: str
    search_relevance: float = 0.0
    extraction_method: str = "tavily"
    trafilatura_score: float = 0.0
    has_title: bool = False
    has_author: bool = False
    has_date: bool = False
    normalized_url: str | None = None
    quality_score: float = 0.0
    rank_score: float = 0.0


def _text(value: Any) -> str:
    """Return normalized text for provider fields."""

    return value.strip() if isinstance(value, str) else ""


def _number(value: Any) -> float:
    """Convert optional extractor scoring metadata without failing extraction."""

    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _source_from_content(
    result: SearchResult,
    content: str,
    *,
    method: str,
    title: str | None = None,
    trafilatura_score: float = 0.0,
    has_title: bool | None = None,
    has_author: bool = False,
    has_date: bool = False,
) -> Source | None:
    """Create a source only when extraction produced useful text."""

    cleaned = _text(content)
    if not cleaned:
        return None
    source_title = _text(title) or result.title or result.url
    return Source(
        title=source_title,
        url=result.url,
        content=cleaned,
        search_relevance=result.score,
        extraction_method=method,
        trafilatura_score=max(0.0, min(1.0, trafilatura_score)),
        has_title=bool(source_title) if has_title is None else has_title,
        has_author=has_author,
        has_date=has_date,
    )


def _extract_tavily_text(payload: Any) -> str:
    """Read the first non-empty content field from a Tavily extract response."""

    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        return ""
    for item in payload["results"]:
        if not isinstance(item, dict):
            continue
        content = _text(item.get("raw_content")) or _text(item.get("content"))
        if content:
            return content
    return ""


def _extract_trafilatura(html: str, url: str) -> dict[str, Any] | None:
    """Extract text plus metadata from downloaded HTML."""

    try:
        extracted = trafilatura.extract(
            html,
            url=url,
            output_format="json",
            with_metadata=True,
        )
    except Exception:
        return None
    if not extracted:
        return None
    if isinstance(extracted, str):
        try:
            payload = json.loads(extracted)
        except json.JSONDecodeError:
            return {"text": extracted}
    elif isinstance(extracted, dict):
        payload = extracted
    else:
        return None
    return payload if isinstance(payload, dict) else None


def _source_from_payload(
    result: SearchResult, payload: dict[str, Any], method: str
) -> Source | None:
    """Build a source from a trafilatura payload produced from any fetcher."""

    content = _text(payload.get("text")) or _text(payload.get("raw_text"))
    return _source_from_content(
        result,
        content,
        method=method,
        title=_text(payload.get("title")) or result.title,
        trafilatura_score=_number(payload.get("score")),
        has_title=bool(_text(payload.get("title"))),
        has_author=bool(_text(payload.get("author"))),
        has_date=bool(_text(payload.get("date"))),
    )


async def _fetch_with_scrapling(
    result: SearchResult, timeout_seconds: float
) -> tuple[Source | None, str | None]:
    """Fetch a page through Scrapling and parse it when Tavily and HTTP both fail."""

    html = await fetch_page_html(result.url, timeout_seconds=timeout_seconds)
    if not html:
        return None, None
    payload = _extract_trafilatura(html, result.url)
    if payload is None:
        return None, None
    source = _source_from_payload(result, payload, method="scrapling")
    if source is None:
        return None, None
    return source, None


async def _fetch_one(
    result: SearchResult,
    *,
    tavily_client: AsyncTavilyClient | Any | None,
    http_client: httpx.AsyncClient,
    mock_mode: bool,
    tavily_timeout_seconds: float,
    http_timeout_seconds: float,
    scrapling_fallback: bool = False,
    scrapling_timeout_seconds: float = 15.0,
) -> tuple[Source | None, str | None]:
    """Extract one result, swallowing failures at the source boundary."""

    if mock_mode:
        page = page_for_url(result.url)
        content = page.text if page is not None else result.content
        source = _source_from_content(result, content, method="mock")
        if source is None:
            logger.warning("Skipping source with no fixture content: %s", result.url)
            return None, "fixture_content_empty"
        return source, None

    if tavily_client is not None:
        try:
            payload = await asyncio.wait_for(
                tavily_client.extract([result.url]),
                timeout=tavily_timeout_seconds,
            )
            content = _extract_tavily_text(payload)
            source = _source_from_content(result, content, method="tavily")
            if source is not None:
                return source, None
        except TimeoutError:
            logger.warning("Tavily extract timed out; trying HTTP fallback: %s", result.url)
        except Exception:
            logger.warning("Tavily extract failed; trying HTTP fallback: %s", result.url)

    try:
        response = await http_client.get(
            result.url,
            headers={"User-Agent": MOBILE_USER_AGENT},
            timeout=http_timeout_seconds,
            follow_redirects=True,
        )
        response.raise_for_status()
        payload = _extract_trafilatura(response.text, result.url)
        if payload is None:
            raise ValueError("trafilatura returned no content")
        source = _source_from_payload(result, payload, method="http")
        if source is None:
            raise ValueError("trafilatura returned empty text")
        return source, None
    except Exception as exc:
        if scrapling_fallback:
            logger.warning(
                "HTTP extraction failed (%s); trying Scrapling: %s",
                type(exc).__name__,
                result.url,
            )
            scrapling_source, _ = await _fetch_with_scrapling(result, scrapling_timeout_seconds)
            if scrapling_source is not None:
                return scrapling_source, None
        logger.warning(
            "Skipping source after extraction failure (%s): %s",
            type(exc).__name__,
            result.url,
        )
        return None, f"{type(exc).__name__}: {exc}"[:240]


async def fetch_sources(
    results: Sequence[SearchResult],
    *,
    tavily_client: AsyncTavilyClient | Any | None = None,
    http_client: httpx.AsyncClient | None = None,
    mock_mode: bool = False,
    tavily_timeout_seconds: float = 15.0,
    http_timeout_seconds: float = 10.0,
    scrapling_fallback: bool = False,
    scrapling_timeout_seconds: float = 15.0,
    on_source_skipped: Any | None = None,
) -> list[Source]:
    """Fetch all sources concurrently and skip individual failures safely."""

    if not results:
        return []
    owns_http_client = http_client is None
    client = http_client or httpx.AsyncClient()
    try:
        outcomes = await asyncio.gather(
            *(
                _fetch_one(
                    result,
                    tavily_client=tavily_client,
                    http_client=client,
                    mock_mode=mock_mode,
                    tavily_timeout_seconds=tavily_timeout_seconds,
                    http_timeout_seconds=http_timeout_seconds,
                    scrapling_fallback=scrapling_fallback,
                    scrapling_timeout_seconds=scrapling_timeout_seconds,
                )
                for result in results
            )
        )
    finally:
        if owns_http_client:
            await client.aclose()
    sources: list[Source] = []
    for result, (source, reason) in zip(results, outcomes, strict=True):
        if source is not None:
            sources.append(source)
        elif on_source_skipped is not None:
            await on_source_skipped(result, reason or "source_unavailable")
    return sources
