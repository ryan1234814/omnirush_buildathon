"""Run snapshot persistence tests."""

from datetime import UTC, datetime

from app.models import ReportRun
from app.storage import load_snapshots, save_snapshot


def test_snapshot_round_trips_through_atomic_json(tmp_path) -> None:
    snapshot = ReportRun(
        id="run-1",
        topic="topic",
        status="completed",
        report_md="# Report",
        created_at=datetime.now(UTC),
    )

    save_snapshot(snapshot, tmp_path)
    loaded = load_snapshots(tmp_path)

    assert len(loaded) == 1
    assert loaded[0].id == "run-1"
    assert loaded[0].report_md == "# Report"
