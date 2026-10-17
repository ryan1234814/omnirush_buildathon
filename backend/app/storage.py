"""Atomic JSON persistence for report snapshots."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from app.models import ReportRun

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
    snapshots: list[ReportRun] = []
    for path in sorted(directory.glob("*.json")):
        try:
            snapshots.append(ReportRun.model_validate_json(path.read_text(encoding="utf-8")))
        except (OSError, ValueError) as exc:
            logger.warning("Ignoring unreadable run snapshot %s (%s)", path, type(exc).__name__)
    return snapshots
