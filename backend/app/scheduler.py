"""Small JSON-backed recurring report scheduler."""

from __future__ import annotations

import asyncio
import calendar
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

from app.config import Settings
from app.events.bus import EventBus
from app.models import ReportRun, Schedule, ScheduleCreate, ScheduleFrequency
from app.pipeline.orchestrator import run_pipeline
from app.storage import load_schedules, save_schedules, save_snapshot


def _values(field: str, minimum: int, maximum: int) -> set[int]:
    """Parse the practical cron subset used by the scheduler."""

    values: set[int] = set()
    for part in field.split(","):
        if part == "*":
            values.update(range(minimum, maximum + 1))
            continue
        if part.startswith("*/"):
            step = int(part[2:])
            if step < 1:
                raise ValueError("cron step must be positive")
            values.update(range(minimum, maximum + 1, step))
            continue
        if "-" in part:
            start, end = (int(value) for value in part.split("-", 1))
            if start > end:
                raise ValueError("cron range must be ascending")
            values.update(range(start, end + 1))
            continue
        values.add(int(part))
    if not values or min(values) < minimum or max(values) > maximum:
        raise ValueError("cron value is outside its field range")
    return values


def cron_matches(expression: str, moment: datetime) -> bool:
    """Match a five-field UTC cron expression."""

    fields = expression.split()
    if len(fields) != 5:
        raise ValueError("cron must contain five fields")
    minute = _values(fields[0], 0, 59)
    hour = _values(fields[1], 0, 23)
    day = _values(fields[2], 1, 31)
    month = _values(fields[3], 1, 12)
    weekday = _values(fields[4].replace("7", "0"), 0, 6)
    cron_weekday = (moment.weekday() + 1) % 7
    return (
        moment.minute in minute
        and moment.hour in hour
        and moment.day in day
        and moment.month in month
        and cron_weekday in weekday
    )


def _add_one_month(moment: datetime) -> datetime:
    """Advance a timestamp by one calendar month, clamping overflowing days."""

    month_index = moment.month - 1 + 1
    year = moment.year + month_index // 12
    month = month_index % 12 + 1
    day = min(moment.day, calendar.monthrange(year, month)[1])
    return moment.replace(year=year, month=month, day=day)


def next_run_at(expression: str | None, frequency: str | None, after: datetime) -> datetime:
    """Return the next interval or cron occurrence after ``after``."""

    after = after.astimezone(UTC).replace(second=0, microsecond=0)
    if frequency == ScheduleFrequency.ONCE.value:
        return after + timedelta(minutes=1)
    if frequency:
        delta = {
            ScheduleFrequency.HOURLY.value: timedelta(hours=1),
            ScheduleFrequency.DAILY.value: timedelta(days=1),
            ScheduleFrequency.WEEKLY.value: timedelta(days=7),
        }.get(frequency)
        if delta is not None:
            return after + delta
        if frequency == ScheduleFrequency.MONTHLY.value:
            return _add_one_month(after)
        raise ValueError(f"unknown schedule frequency: {frequency}")
    candidate = after + timedelta(minutes=1)
    for _ in range(60 * 24 * 366):
        if cron_matches(expression or "", candidate):
            return candidate
        candidate += timedelta(minutes=1)
    raise ValueError("cron has no occurrence within one year")


class SchedulerService:
    """Create due report runs and persist schedule cursors."""

    def __init__(self, settings: Settings, bus: EventBus, tasks: set[object]) -> None:
        self.settings = settings
        self.bus = bus
        self.tasks = tasks

    def list(self) -> list[Schedule]:
        return load_schedules(self.settings.runs_dir)

    def create(self, payload: ScheduleCreate, now: datetime | None = None) -> Schedule:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        frequency = payload.frequency.value if payload.frequency else None
        first = next_run_at(payload.cron, frequency, current)
        schedule = Schedule(
            id=uuid.uuid4().hex,
            created_at=current,
            next_run_at=first,
            **payload.model_dump(),
        )
        schedules = self.list()
        schedules.append(schedule)
        save_schedules(schedules, self.settings.runs_dir)
        return schedule

    def delete(self, schedule_id: str) -> bool:
        schedules = self.list()
        remaining = [schedule for schedule in schedules if schedule.id != schedule_id]
        if len(remaining) == len(schedules):
            return False
        save_schedules(remaining, self.settings.runs_dir)
        return True

    async def tick(self, now: datetime | None = None) -> list[str]:
        """Start each due schedule once; repeated ticks cannot create unbounded work."""

        current = (now or datetime.now(UTC)).astimezone(UTC)
        schedules = self.list()
        started: list[str] = []
        changed = False
        for schedule in schedules:
            if not schedule.enabled or schedule.next_run_at > current:
                continue
            run = ReportRun(
                id=uuid.uuid4().hex,
                topic=schedule.topic,
                schedule_id=schedule.id,
                created_at=current,
            )
            await self.bus.register(run)
            save_snapshot(run, self.settings.runs_dir)
            task = asyncio.create_task(run_pipeline(run.id, self.bus, self.settings, self.tasks))
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)
            schedule.last_run_at = current
            schedule.last_run_id = run.id
            if schedule.frequency == ScheduleFrequency.ONCE:
                schedule.enabled = False
            else:
                schedule.next_run_at = next_run_at(schedule.cron, schedule.frequency.value, current)
            started.append(run.id)
            changed = True
        if changed:
            save_schedules(schedules, self.settings.runs_dir)
        return started


def due_schedule_ids(schedules: Iterable[Schedule], now: datetime) -> list[str]:
    """Pure helper used by tests and operators to inspect due work."""

    current = now.astimezone(UTC)
    return [
        schedule.id
        for schedule in schedules
        if schedule.enabled and schedule.next_run_at <= current
    ]
