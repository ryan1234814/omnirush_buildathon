"""Stage-based report orchestration for the API and mock checkpoint."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Sequence

from openai import AsyncOpenAI
from tavily import AsyncTavilyClient

from app.config import Settings
from app.events.bus import EventBus
from app.models import ReportRun, Stage, StageTiming
from app.pipeline.citations import build_registry, validate_report
from app.pipeline.extract import fetch_sources
from app.pipeline.query_planner import QueryPlanner
from app.pipeline.ranker import normalize_url, rank_sources
from app.pipeline.report_md import assemble
from app.pipeline.search import (
    MockSearch,
    SearchCallBudget,
    SearchError,
    SearchProvider,
    SearchResult,
    TavilySearch,
)
from app.pipeline.synthesizer import stream_report
from app.storage import save_snapshot

logger = logging.getLogger(__name__)
NO_SOURCES_MESSAGE = "No sources found. Try a different topic."
PARTIAL_SYNTHESIS_NOTE = (
    "\n\n> **Partial report:** Synthesis stopped before completion. "
    "The text above is the deterministic partial output available at this time.\n"
)


def _unique_results(results: Sequence[SearchResult]) -> list[SearchResult]:
    """Deduplicate overlapping planned-query results before extraction."""

    unique: dict[str, SearchResult] = {}
    for result in results:
        key = normalize_url(result.url)
        current = unique.get(key)
        if current is None or result.score > current.score:
            unique[key] = result
    return list(unique.values())


def _provider(
    settings: Settings,
    call_budget: SearchCallBudget | None = None,
) -> tuple[SearchProvider, AsyncTavilyClient | None]:
    """Create the configured search provider and optional Tavily client."""

    if settings.mock_mode or settings.search_provider == "mock":
        return MockSearch(call_budget=call_budget), None
    if settings.search_provider != "tavily" or not settings.tavily_api_key:
        raise SearchError("Tavily search is not configured")
    client = AsyncTavilyClient(api_key=settings.tavily_api_key)
    return (
        TavilySearch(
            settings.tavily_api_key,
            client=client,
            retry_backoff_seconds=settings.search_retry_backoff_seconds,
            call_budget=call_budget,
        ),
        client,
    )


async def _persist(bus: EventBus, run_id: str, settings: Settings) -> ReportRun:
    """Persist and return the latest run snapshot."""

    snapshot = await bus.get_snapshot(run_id)
    save_snapshot(snapshot, settings.runs_dir)
    return snapshot


def _stage_budget(settings: Settings, stage: Stage) -> float | None:
    """Return the configured latency budget for a measured stage."""

    return {
        Stage.PLANNING: settings.planning_budget_seconds,
        Stage.SEARCHING: settings.search_budget_seconds,
        Stage.EXTRACTING: settings.extraction_budget_seconds,
        Stage.SYNTHESIZING: settings.synthesis_budget_seconds,
    }.get(stage)


def _budget_status(snapshot: ReportRun, total_budget_seconds: float) -> str:
    """Calculate the aggregate budget status exposed in snapshots and events."""

    if snapshot.total_elapsed_ms / 1000 > total_budget_seconds:
        return "exceeded"
    if any(timing.within_budget is False for timing in snapshot.stage_timings.values()):
        return "exceeded"
    return "within_budget"


async def _start_stage(
    bus: EventBus,
    run_id: str,
    stage: Stage,
    settings: Settings,
    stage_started: dict[Stage, float],
) -> None:
    """Set stage state and emit a stage-start event."""

    stage_started[stage] = time.monotonic()
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
    *,
    stage_started: dict[Stage, float],
    pipeline_started: float,
) -> None:
    """Persist a stage boundary and emit a stage-completed event."""

    elapsed_ms = max(0.0, (time.monotonic() - stage_started[stage]) * 1000)
    budget_seconds = _stage_budget(settings, stage)
    within_budget = budget_seconds is None or elapsed_ms / 1000 <= budget_seconds
    snapshot = await bus.get_snapshot(run_id)
    snapshot.stage_timings[stage.value] = StageTiming(
        elapsed_ms=round(elapsed_ms, 3),
        budget_seconds=budget_seconds,
        within_budget=within_budget if budget_seconds is not None else None,
    )
    snapshot.total_elapsed_ms = round(max(0.0, time.monotonic() - pipeline_started) * 1000, 3)
    snapshot.budget_status = _budget_status(snapshot, settings.total_budget_seconds)
    await bus.update_snapshot(snapshot)
    await _persist(bus, run_id, settings)
    await bus.publish(
        run_id,
        "stage_completed",
        {
            "stage": stage.value,
            "elapsed_ms": round(elapsed_ms, 3),
            "budget_seconds": budget_seconds,
            "within_budget": within_budget if budget_seconds is not None else None,
            "total_elapsed_ms": snapshot.total_elapsed_ms,
            "budget_status": snapshot.budget_status,
            "persisted": True,
            **(payload or {}),
        },
    )


async def _search_all(
    provider: SearchProvider,
    queries: Sequence[str],
    max_results: int = 8,
    max_calls: int = 8,
) -> list[SearchResult]:
    """Search planned queries concurrently."""

    planned_queries = list(queries)[: max(0, max_calls)]
    batches = await asyncio.gather(
        *(provider.search(query, max_results) for query in planned_queries)
    )
    return [result for batch in batches for result in batch]


async def _finish_without_synthesis(
    bus: EventBus,
    run_id: str,
    settings: Settings,
    *,
    outcome: str,
    message: str,
    event_type: str,
    pipeline_started: float,
) -> None:
    """Complete a run with an explicit empty-source outcome."""

    snapshot = await bus.get_snapshot(run_id)
    snapshot.status = "completed"
    snapshot.stage = Stage.DONE
    snapshot.outcome = outcome
    snapshot.message = message
    snapshot.error = None
    snapshot.total_elapsed_ms = round(max(0.0, time.monotonic() - pipeline_started) * 1000, 3)
    snapshot.budget_status = _budget_status(snapshot, settings.total_budget_seconds)
    await bus.update_snapshot(snapshot)
    save_snapshot(snapshot, settings.runs_dir)
    await bus.publish(
        run_id,
        event_type,
        {"message": message, "outcome": outcome, "total_elapsed_ms": snapshot.total_elapsed_ms},
    )
    await bus.publish(
        run_id,
        "run_completed",
        {
            "stage": Stage.DONE.value,
            "outcome": outcome,
            "message": message,
            "budget_status": snapshot.budget_status,
            "search_calls": snapshot.search_calls,
            "max_search_calls": snapshot.max_search_calls,
        },
    )


async def run_pipeline(run_id: str, bus: EventBus, settings: Settings) -> None:
    """Run every report stage and convert failures into a failed run snapshot."""

    active_stage = Stage.PLANNING
    pipeline_started = time.monotonic()
    stage_started: dict[Stage, float] = {}
    try:
        snapshot = await bus.get_snapshot(run_id)
        snapshot.status = "running"
        await bus.update_snapshot(snapshot)
        save_snapshot(snapshot, settings.runs_dir)

        active_stage = Stage.PLANNING
        await _start_stage(bus, run_id, active_stage, settings, stage_started)
        planner = QueryPlanner.from_settings(settings)
        queries = await planner.plan(snapshot.topic)
        await _complete_stage(
            bus,
            run_id,
            active_stage,
            settings,
            {"sub_queries": queries},
            stage_started=stage_started,
            pipeline_started=pipeline_started,
        )

        active_stage = Stage.SEARCHING
        await _start_stage(bus, run_id, active_stage, settings, stage_started)
        search_budget = SearchCallBudget(settings.max_search_calls)
        provider, tavily_client = _provider(settings, search_budget)
        search_results = await _search_all(provider, queries, max_calls=settings.max_search_calls)
        unique_results = _unique_results(search_results)
        search_snapshot = await bus.get_snapshot(run_id)
        search_snapshot.search_calls = search_budget.calls
        search_snapshot.max_search_calls = search_budget.max_calls
        await bus.update_snapshot(search_snapshot)
        save_snapshot(search_snapshot, settings.runs_dir)
        logger.info(
            "Search completed for run %s: calls=%d cap=%d results=%d",
            run_id,
            search_budget.calls,
            search_budget.max_calls,
            len(unique_results),
        )
        await _complete_stage(
            bus,
            run_id,
            active_stage,
            settings,
            {
                "results": len(unique_results),
                "search_calls": search_budget.calls,
                "max_search_calls": search_budget.max_calls,
                "search_calls_capped": search_budget.calls >= search_budget.max_calls,
            },
            stage_started=stage_started,
            pipeline_started=pipeline_started,
        )
        await bus.publish(
            run_id,
            "search_completed",
            {
                "results": len(unique_results),
                "search_calls": search_budget.calls,
                "max_search_calls": search_budget.max_calls,
                "capped": search_budget.calls >= search_budget.max_calls,
            },
        )
        if not unique_results:
            await bus.publish(
                run_id,
                "no_results",
                {"message": NO_SOURCES_MESSAGE, "outcome": "no_results"},
            )
            await _finish_without_synthesis(
                bus,
                run_id,
                settings,
                outcome="no_results",
                message=NO_SOURCES_MESSAGE,
                event_type="no_results_completed",
                pipeline_started=pipeline_started,
            )
            return

        active_stage = Stage.EXTRACTING
        await _start_stage(bus, run_id, active_stage, settings, stage_started)

        async def source_skipped(result: SearchResult, reason: str) -> None:
            await bus.publish(
                run_id,
                "source_skipped",
                {"url": result.url, "kind": "dead", "reason": reason},
            )

        extracted = await fetch_sources(
            unique_results,
            tavily_client=tavily_client,
            mock_mode=settings.mock_mode or settings.search_provider == "mock",
            on_source_skipped=source_skipped,
        )
        extraction_snapshot = await bus.get_snapshot(run_id)
        extraction_snapshot.attempted_sources = len(unique_results)
        extraction_snapshot.succeeded_sources = len(extracted)
        await bus.update_snapshot(extraction_snapshot)
        save_snapshot(extraction_snapshot, settings.runs_dir)
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
        await _complete_stage(
            bus,
            run_id,
            active_stage,
            settings,
            {
                "sources": len(extracted),
                "attempted_sources": len(unique_results),
                "succeeded_sources": len(extracted),
            },
            stage_started=stage_started,
            pipeline_started=pipeline_started,
        )

        active_stage = Stage.RANKING
        await _start_stage(bus, run_id, active_stage, settings, stage_started)
        ranked = rank_sources(extracted, top_k=settings.top_k)
        registry = build_registry(
            ranked,
            max_context_tokens=settings.synthesis_context_tokens,
        )
        snapshot = await bus.get_snapshot(run_id)
        snapshot.sources = registry.entries
        await bus.update_snapshot(snapshot)
        await _complete_stage(
            bus,
            run_id,
            active_stage,
            settings,
            {"sources": len(ranked)},
            stage_started=stage_started,
            pipeline_started=pipeline_started,
        )
        if not registry.entries:
            await _finish_without_synthesis(
                bus,
                run_id,
                settings,
                outcome="no_sources",
                message=NO_SOURCES_MESSAGE,
                event_type="no_sources_completed",
                pipeline_started=pipeline_started,
            )
            return

        active_stage = Stage.SYNTHESIZING
        await _start_stage(bus, run_id, active_stage, settings, stage_started)
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
        synthesis_error: Exception | None = None
        try:
            async for token in stream_report(
                snapshot.topic,
                registry,
                client=client,
                model=settings.llm_model,
                mock_mode=settings.mock_mode,
                timeout_seconds=settings.synthesis_budget_seconds,
            ):
                chunks.append(token)
                await bus.publish(run_id, "report_token", {"token": token})
        except Exception as exc:
            synthesis_error = exc
        synthesis_partial = synthesis_error is not None
        raw_body = "".join(chunks)
        if synthesis_partial:
            raw_body = (raw_body.rstrip() + PARTIAL_SYNTHESIS_NOTE).strip()
            await bus.publish(
                run_id,
                "synthesis_partial",
                {
                    "reason": type(synthesis_error).__name__,
                    "message": PARTIAL_SYNTHESIS_NOTE.strip(),
                    "partial_chars": len(raw_body),
                },
            )
        body, removed_cites = validate_report(raw_body, registry)
        if removed_cites:
            await bus.publish(run_id, "citations_removed", {"ids": removed_cites})
        await _complete_stage(
            bus,
            run_id,
            active_stage,
            settings,
            {
                "removed_citations": len(removed_cites),
                "partial": synthesis_partial,
            },
            stage_started=stage_started,
            pipeline_started=pipeline_started,
        )

        active_stage = Stage.RENDERING
        await _start_stage(bus, run_id, active_stage, settings, stage_started)
        report = assemble(snapshot.topic, body, registry)
        snapshot = await bus.get_snapshot(run_id)
        snapshot.report_md = report
        snapshot.sources = registry.entries
        await bus.update_snapshot(snapshot)
        await _complete_stage(
            bus,
            run_id,
            active_stage,
            settings,
            stage_started=stage_started,
            pipeline_started=pipeline_started,
        )

        snapshot = await bus.get_snapshot(run_id)
        snapshot.status = "completed"
        snapshot.stage = Stage.DONE
        snapshot.error = None
        snapshot.outcome = "partial" if synthesis_partial else "completed"
        snapshot.message = PARTIAL_SYNTHESIS_NOTE.strip() if synthesis_partial else None
        snapshot.partial = synthesis_partial
        snapshot.total_elapsed_ms = round(max(0.0, time.monotonic() - pipeline_started) * 1000, 3)
        snapshot.budget_status = _budget_status(snapshot, settings.total_budget_seconds)
        await bus.update_snapshot(snapshot)
        save_snapshot(snapshot, settings.runs_dir)
        await bus.publish(
            run_id,
            "run_completed",
            {
                "stage": Stage.DONE.value,
                "outcome": snapshot.outcome,
                "partial": snapshot.partial,
                "budget_status": snapshot.budget_status,
                "total_elapsed_ms": snapshot.total_elapsed_ms,
                "search_calls": snapshot.search_calls,
                "max_search_calls": snapshot.max_search_calls,
                "attempted_sources": snapshot.attempted_sources,
                "succeeded_sources": snapshot.succeeded_sources,
            },
        )
        logger.info(
            "Report run completed: run_id=%s outcome=%s total_ms=%.1f search_calls=%d/%d",
            run_id,
            snapshot.outcome,
            snapshot.total_elapsed_ms,
            snapshot.search_calls,
            snapshot.max_search_calls,
        )
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
