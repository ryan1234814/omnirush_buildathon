"""Atomic JSON persistence for report snapshots."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from app.models import Notification, ReportRun, Schedule

logger = logging.getLogger(__name__)


def _runs_path(runs_dir: str | Path, run_id: str) -> Path:
    """Return the snapshot path for a run."""

    return Path(runs_dir) / f"{run_id}.json"


def save_snapshot(snapshot: ReportRun, runs_dir: str | Path) -> None:
    """Write a snapshot atomically so a crash cannot leave partial JSON."""

    directory = Path(runs_dir)
    directory.mkdir(parents=True, exist_ok=True)
    target = _runs_path(directory, snapshot.id)
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(snapshot.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, target)


def load_snapshots(runs_dir: str | Path) -> list[ReportRun]:
    """Load valid snapshots, ignoring malformed files with a warning."""

    directory = Path(runs_dir)
    if not directory.exists():
        return []
    reserved = {_schedules_path(directory).name, _notifications_path(directory).name}
    snapshots: list[ReportRun] = []
    for path in sorted(directory.glob("*.json")):
        if path.name in reserved:
            continue
        try:
            snapshots.append(ReportRun.model_validate_json(path.read_text(encoding="utf-8")))
        except (OSError, ValueError) as exc:
            logger.warning("Ignoring unreadable run snapshot %s (%s)", path, type(exc).__name__)
    return snapshots


def _schedules_path(runs_dir: str | Path) -> Path:
    """Return the single JSON file containing recurring schedules."""

    return Path(runs_dir) / "schedules.json"


def save_schedules(schedules: list[Schedule], runs_dir: str | Path) -> None:
    """Persist all schedules atomically in one human-readable JSON file."""

    directory = Path(runs_dir)
    directory.mkdir(parents=True, exist_ok=True)
    target = _schedules_path(directory)
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps([schedule.model_dump(mode="json") for schedule in schedules], indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, target)


def load_schedules(runs_dir: str | Path) -> list[Schedule]:
    """Load persisted schedules, ignoring malformed entries with a warning."""

    path = _schedules_path(runs_dir)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Ignoring unreadable schedules file %s (%s)", path, type(exc).__name__)
        return []
    if not isinstance(payload, list):
        logger.warning("Ignoring schedules file %s: expected an array", path)
        return []
    schedules: list[Schedule] = []
    for item in payload:
        try:
            schedules.append(Schedule.model_validate(item))
        except (TypeError, ValueError) as exc:
            logger.warning("Ignoring malformed schedule (%s)", type(exc).__name__)
    return schedules


def _notifications_path(runs_dir: str | Path) -> Path:
    """Return the single JSON file containing in-app notifications."""

    return Path(runs_dir) / "notifications.json"


def save_notifications(notifications: list[Notification], runs_dir: str | Path) -> None:
    """Persist all notifications atomically in one human-readable JSON file."""

    directory = Path(runs_dir)
    directory.mkdir(parents=True, exist_ok=True)
    target = _notifications_path(directory)
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(
            [notification.model_dump(mode="json") for notification in notifications],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, target)


def load_notifications(runs_dir: str | Path) -> list[Notification]:
    """Load persisted notifications, ignoring malformed entries with a warning."""

    path = _notifications_path(runs_dir)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Ignoring unreadable notifications file %s (%s)", path, type(exc).__name__)
        return []
    if not isinstance(payload, list):
        logger.warning("Ignoring notifications file %s: expected an array", path)
        return []
    notifications: list[Notification] = []
    for item in payload:
        try:
            notifications.append(Notification.model_validate(item))
        except (TypeError, ValueError) as exc:
            logger.warning("Ignoring malformed notification (%s)", type(exc).__name__)
    return notifications
