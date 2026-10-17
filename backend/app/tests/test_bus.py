"""Event bus replay and fan-out tests."""

import asyncio
from datetime import UTC, datetime

import pytest

from app.events.bus import EventBus
from app.models import ReportRun


def run_snapshot() -> ReportRun:
    return ReportRun(id="run-1", topic="topic", created_at=datetime.now(UTC))


@pytest.mark.asyncio
async def test_bus_replays_ordered_events_to_multiple_subscribers() -> None:
    bus = EventBus()
    await bus.register(run_snapshot())
    await bus.publish("run-1", "stage_started", {"stage": "PLANNING"})
    await bus.publish("run-1", "run_completed", {})

    first = [event async for event in bus.stream("run-1", 0)]
    second = [event async for event in bus.stream("run-1", 1)]

    assert [event.seq for event in first] == [1, 2]
    assert [event.type for event in second] == ["run_completed"]


@pytest.mark.asyncio
async def test_bus_fans_out_live_events_without_splitting_them() -> None:
    bus = EventBus()
    await bus.register(run_snapshot())
    first_stream = bus.stream("run-1")
    second_stream = bus.stream("run-1")

    first_wait = asyncio.create_task(first_stream.__anext__())
    second_wait = asyncio.create_task(second_stream.__anext__())
    await asyncio.sleep(0)
    await bus.publish("run-1", "run_completed", {})

    assert (await first_wait).type == "run_completed"
    assert (await second_wait).type == "run_completed"
    await first_stream.aclose()
    await second_stream.aclose()
