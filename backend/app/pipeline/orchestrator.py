"""Stage-based report orchestration for the API and mock checkpoint."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence

from openai import AsyncOpenAI
from tavily import AsyncTavilyClient

from app.config import Settings
from app.events.bus import EventBus
from app.models import ReportRun, Stage
from app.pipeline.citations import build_registry, validate_report
from app.pipeline.extract import fetch_sources
from app.pipeline.query_planner import QueryPlanner
from app.pipeline.ranker import normalize_url, rank_sources
from app.pipeline.report_md import assemble
from app.pipeline.search import MockSearch, SearchError, SearchProvider, SearchResult, TavilySearch
from app.pipeline.synthesizer import stream_report
from app.storage import save_snapshot

logger = logging.getLogger(__name__)


def _unique_results(results: Sequence[SearchResult]) -> list[SearchResult]:
    """Deduplicate overlapping planned-query results before extraction."""

    unique: dict[str, SearchResult] = {}
    for result in results:
        key = normalize_url(result.url)
        current = unique.get(key)
        if current is None or result.score > current.score:
            unique[key] = result
    return list(unique.values())


def _provider(settings: Settings) -> tuple[SearchProvider, AsyncTavilyClient | None]:
    """Create the configured search provider and optional Tavily client."""

    if settings.mock_mode or settings.search_provider == "mock":
        return MockSearch(), None
    if settings.search_provider != "tavily" or not settings.tavily_api_key:
        raise SearchError("Tavily search is not configured")
    client = AsyncTavilyClient(api_key=settings.tavily_api_key)
    return TavilySearch(settings.tavily_api_key, client=client), client


async def _persist(bus: EventBus, run_id: str, settings: Settings) -> ReportRun:
    """Persist and return the latest run snapshot."""

    snapshot = await bus.get_snapshot(run_id)
    save_snapshot(snapshot, settings.runs_dir)
    return snapshot


async def _start_stage(bus: EventBus, run_id: str, stage: Stage, settings: Settings) -> None:
    """Set stage state and emit a stage-start event."""

    snapshot = await bus.get_snapshot(run_id)
    snapshot.stage = stage
    snapshot.status = "running"
    await bus.update_snapshot(snapshot)
    save_snapshot(snapshot, settings.runs_dir)
    await bus.publish(run_id, "stage_started", {"stage": stage.value})


async def _complete_stage(
    bus: EventBus,
    run_id: str,
    stage: Stage,
    settings: Settings,
    payload: dict[str, object] | None = None,
) -> None:
    """Persist a stage boundary and emit a stage-completed event."""

    await _persist(bus, run_id, settings)
    await bus.publish(run_id, "stage_completed", {"stage": stage.value, **(payload or {})})


async def _search_all(
    provider: SearchProvider,
    queries: Sequence[str],
    max_results: int = 8,
) -> list[SearchResult]:
    """Search planned queries concurrently."""

    batches = await asyncio.gather(*(provider.search(query, max_results) for query in queries))
    return [result for batch in batches for result in batch]


async def run_pipeline(run_id: str, bus: EventBus, settings: Settings) -> None:
    """Run every report stage and convert failures into a failed run snapshot."""

    active_stage = Stage.PLANNING
    try:
        snapshot = await bus.get_snapshot(run_id)
        snapshot.status = "running"
        await bus.update_snapshot(snapshot)
        save_snapshot(snapshot, settings.runs_dir)

        active_stage = Stage.PLANNING
        await _start_stage(bus, run_id, active_stage, settings)
        planner = QueryPlanner.from_settings(settings)
        queries = await planner.plan(snapshot.topic)
        await _complete_stage(bus, run_id, active_stage, settings, {"sub_queries": queries})

        active_stage = Stage.SEARCHING
        await _start_stage(bus, run_id, active_stage, settings)
        provider, tavily_client = _provider(settings)
        search_results = await _search_all(provider, queries)
        unique_results = _unique_results(search_results)
        await _complete_stage(
            bus,
            run_id,
            active_stage,
            settings,
            {"results": len(unique_results)},
        )

        active_stage = Stage.EXTRACTING
        await _start_stage(bus, run_id, active_stage, settings)
        extracted = await fetch_sources(
            unique_results,
            tavily_client=tavily_client,
            mock_mode=settings.mock_mode or settings.search_provider == "mock",
        )
        extracted_by_url = {normalize_url(source.url): source for source in extracted}
        for result in unique_results:
            source = extracted_by_url.get(normalize_url(result.url))
            await bus.publish(
                run_id,
                "source_fetched",
                {
                    "url": result.url,
                    "ok": source is not None,
                    "bytes": len(source.content.encode("utf-8")) if source else 0,
                },
            )
        await _complete_stage(bus, run_id, active_stage, settings, {"sources": len(extracted)})

        active_stage = Stage.RANKING
        await _start_stage(bus, run_id, active_stage, settings)
        ranked = rank_sources(extracted, top_k=settings.top_k)
        registry = build_registry(
            ranked,
            max_context_tokens=settings.synthesis_context_tokens,
        )
        snapshot = await bus.get_snapshot(run_id)
        snapshot.sources = registry.entries
        await bus.update_snapshot(snapshot)
        await _complete_stage(bus, run_id, active_stage, settings, {"sources": len(ranked)})

        active_stage = Stage.SYNTHESIZING
        await _start_stage(bus, run_id, active_stage, settings)
        client: AsyncOpenAI | None = None
        if not settings.mock_mode:
            if not settings.llm_configured:
                raise RuntimeError("LLM synthesis is not configured")
            client = AsyncOpenAI(
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url,
                timeout=60.0,
                max_retries=0,
            )
        chunks: list[str] = []
        async for token in stream_report(
            snapshot.topic,
            registry,
            client=client,
            model=settings.llm_model,
            mock_mode=settings.mock_mode,
        ):
            chunks.append(token)
            await bus.publish(run_id, "report_token", {"token": token})
        body, removed_cites = validate_report("".join(chunks), registry)
        if removed_cites:
            await bus.publish(run_id, "citations_removed", {"ids": removed_cites})
        await _complete_stage(
            bus,
            run_id,
            active_stage,
            settings,
            {"removed_citations": len(removed_cites)},
        )

        active_stage = Stage.RENDERING
        await _start_stage(bus, run_id, active_stage, settings)
        report = assemble(snapshot.topic, body, registry)
        snapshot = await bus.get_snapshot(run_id)
        snapshot.report_md = report
        snapshot.sources = registry.entries
        await bus.update_snapshot(snapshot)
        await _complete_stage(bus, run_id, active_stage, settings)

        snapshot = await bus.get_snapshot(run_id)
        snapshot.status = "completed"
        snapshot.stage = Stage.DONE
        snapshot.error = None
        await bus.update_snapshot(snapshot)
        save_snapshot(snapshot, settings.runs_dir)
        await bus.publish(run_id, "run_completed", {"stage": Stage.DONE.value})
    except Exception as exc:
        logger.error("Report run failed at %s (%s)", active_stage.value, type(exc).__name__)
        try:
            snapshot = await bus.get_snapshot(run_id)
            snapshot.status = "failed"
            snapshot.stage = Stage.FAILED
            snapshot.error = f"Pipeline failed during {active_stage.value}: {type(exc).__name__}"
            await bus.update_snapshot(snapshot)
            save_snapshot(snapshot, settings.runs_dir)
            await bus.publish(
                run_id,
                "stage_failed",
                {"stage": active_stage.value, "error": snapshot.error},
            )
            await bus.publish(
                run_id,
                "run_failed",
                {"stage": active_stage.value, "error": snapshot.error},
            )
        except Exception as persist_exc:
            logger.error(
                "Could not persist failed report run %s (%s)",
                run_id,
                type(persist_exc).__name__,
            )
