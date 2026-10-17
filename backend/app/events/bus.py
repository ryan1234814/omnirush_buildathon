"""In-memory run event bus with replay and multi-subscriber fan-out."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.models import ReportRun, RunEvent

TERMINAL_EVENTS = {"run_completed", "run_failed"}


@dataclass
class _RunChannel:
    """Mutable event state for one report run."""

    snapshot: ReportRun
    history: list[RunEvent] = field(default_factory=list)
    subscribers: set[asyncio.Queue[RunEvent]] = field(default_factory=set)
    next_seq: int = 1


class EventBus:
    """Publish events to all subscribers while retaining process-local history."""

    def __init__(self) -> None:
        self._channels: dict[str, _RunChannel] = {}
        self._lock = asyncio.Lock()

    async def register(self, snapshot: ReportRun) -> None:
        """Register a new run snapshot before its background task starts."""

        async with self._lock:
            self._channels[snapshot.id] = _RunChannel(snapshot=snapshot)

    def restore(self, snapshot: ReportRun) -> None:
        """Restore a snapshot during application startup."""

        channel = _RunChannel(snapshot=snapshot)
        if snapshot.status == "completed":
            channel.history.append(
                RunEvent(
                    seq=1,
                    type="run_completed",
                    payload={"restored": True},
                    created_at=snapshot.created_at,
                )
            )
            channel.next_seq = 2
        elif snapshot.status == "failed":
            channel.history.append(
                RunEvent(
                    seq=1,
                    type="run_failed",
                    payload={"restored": True},
                    created_at=snapshot.created_at,
                )
            )
            channel.next_seq = 2
        self._channels[snapshot.id] = channel

    async def get_snapshot(self, run_id: str) -> ReportRun:
        """Return an independent snapshot or raise ``KeyError``."""

        async with self._lock:
            channel = self._channels[run_id]
            return channel.snapshot.model_copy(deep=True)

    async def update_snapshot(self, snapshot: ReportRun) -> None:
        """Replace the current snapshot without emitting an event."""

        async with self._lock:
            self._channels[snapshot.id].snapshot = snapshot.model_copy(deep=True)

    async def publish(self, run_id: str, event_type: str, payload: dict[str, object]) -> RunEvent:
        """Publish one ordered event to history and every active subscriber."""

        async with self._lock:
            channel = self._channels[run_id]
            event = RunEvent(
                seq=channel.next_seq,
                type=event_type,
                payload=payload,
                created_at=datetime.now(UTC),
            )
            channel.next_seq += 1
            channel.history.append(event)
            for subscriber in channel.subscribers:
                subscriber.put_nowait(event)
            return event

    async def stream(self, run_id: str, last_event_id: int = 0) -> AsyncIterator[RunEvent]:
        """Replay missed events, then stream live events until the run terminates."""

        queue: asyncio.Queue[RunEvent] = asyncio.Queue()
        async with self._lock:
            channel = self._channels[run_id]
            replay = [event for event in channel.history if event.seq > last_event_id]
            channel.subscribers.add(queue)
        try:
            if not replay and channel.snapshot.status in {"completed", "failed"}:
                return
            for event in replay:
                yield event
                if event.type in TERMINAL_EVENTS:
                    return
            while True:
                event = await queue.get()
                yield event
                if event.type in TERMINAL_EVENTS:
                    return
        finally:
            async with self._lock:
                channel = self._channels.get(run_id)
                if channel is not None:
                    channel.subscribers.discard(queue)
