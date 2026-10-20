"""Run the Phase 3 planner, search, extraction, and ranking smoke check.

Usage from ``backend/``::

    uv run python -m scripts.integration_check "quantum computing 2026"

The script deliberately reports failures as one-line messages and never emits
a traceback. Real Tavily extraction is used only for a real Tavily provider;
mock mode remains entirely offline.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict
from typing import Any

from tavily import AsyncTavilyClient

from app.config import Settings, get_settings
from app.pipeline.extract import fetch_sources
from app.pipeline.query_planner import QueryPlanner
from app.pipeline.ranker import normalize_url, rank_sources
from app.pipeline.scrapling_search import ScraplingSearch
from app.pipeline.search import (
    FallbackSearch,
    MockSearch,
    SearchConfigurationError,
    SearchError,
    SearchProvider,
    SearchResult,
    TavilySearch,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check planner, search, extraction, and ranking")
    parser.add_argument("topic", help="research topic to plan and search")
    parser.add_argument(
        "--max-results",
        type=int,
        default=8,
        help="results per sub-query (default: 8)",
    )
    return parser


def _extract_clean_text(payload: Any) -> str:
    """Get the first cleaned text from Tavily's extract response."""

    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise SearchError("Tavily returned an invalid extract response")
    for item in payload["results"]:
        if not isinstance(item, dict):
            continue
        text = item.get("raw_content") or item.get("content")
        if isinstance(text, str) and text.strip():
            return text.strip()
    raise SearchError("Tavily returned no cleaned extract text")


def _provider(settings: Settings) -> tuple[SearchProvider, AsyncTavilyClient | None]:
    """Create the selected provider and, for Tavily, retain its client for extract."""

    if settings.mock_mode or settings.search_provider == "mock":
        return MockSearch(), None
    if settings.search_provider != "tavily":
        raise SearchError(
            f"Search provider '{settings.search_provider}' is not implemented "
            "for this Phase 2 check"
        )
    if not settings.tavily_api_key:
        raise SearchConfigurationError("Tavily search is not configured: TAVILY_API_KEY is missing")
    client = AsyncTavilyClient(api_key=settings.tavily_api_key)
    primary = TavilySearch(settings.tavily_api_key, client=client)
    if not settings.scrapling_fallback:
        return primary, client
    provider: SearchProvider = FallbackSearch(
        primary, ScraplingSearch(timeout_seconds=settings.scrapling_timeout_seconds)
    )
    return provider, client


async def _search_all(
    provider: SearchProvider,
    queries: Sequence[str],
    max_results: int,
) -> list[SearchResult]:
    """Search all planned queries concurrently while preserving planned order."""

    batches = await asyncio.gather(
        *(provider.search(query, max_results) for query in queries),
    )
    return [result for batch in batches for result in batch]


def _deduplicate_results(results: Sequence[SearchResult]) -> list[SearchResult]:
    """Avoid repeated extraction calls when query plans overlap."""

    unique: dict[str, SearchResult] = {}
    for result in results:
        key = normalize_url(result.url)
        current = unique.get(key)
        if current is None or result.score > current.score:
            unique[key] = result
    return list(unique.values())


async def run_check(topic: str, max_results: int, settings: Settings) -> int:
    """Run the smoke check and return a shell-friendly exit status."""

    if max_results < 1:
        print("Error: --max-results must be at least 1", file=sys.stderr)
        return 2

    planner = QueryPlanner.from_settings(settings)
    queries = await planner.plan(topic)
    print("Planned sub-queries:")
    for query in queries:
        print(f"- {query}")

    try:
        provider, tavily_client = _provider(settings)
        results = await _search_all(provider, queries, max_results)
    except SearchError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print("\nSearch results:")
    print(json.dumps([asdict(result) for result in results], indent=2))
    if not results:
        print("\nNo search results; extraction skipped.")
        return 1

    unique_results = _deduplicate_results(results)
    sources = await fetch_sources(
        unique_results,
        tavily_client=tavily_client,
        mock_mode=settings.mock_mode or settings.search_provider == "mock",
    )
    ranked = rank_sources(sources, top_k=settings.top_k)
    print(f"\nExtracted sources: {len(sources)}")
    print(f"Ranked sources (top_k={settings.top_k}):")
    print(json.dumps([asdict(source) for source in ranked], indent=2))
    if not ranked:
        print("\nNo sources could be extracted; ranking skipped.")
        return 1
    first = ranked[0]
    print(f"\nExtracted text preview from {first.url}:")
    print(first.content[:1000])
    return 0


async def _main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return await run_check(args.topic, args.max_results, get_settings())
    except Exception as exc:
        print(f"Error: integration check failed ({type(exc).__name__})", file=sys.stderr)
        return 1


def main(argv: Sequence[str] | None = None) -> int:
    """Synchronous entry point for the module and tests."""

    return asyncio.run(_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
