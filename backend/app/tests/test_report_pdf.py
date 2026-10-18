"""API tests for PDF readiness, generation, and cache behavior."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.api import reports
from app.config import Settings
from app.events.bus import EventBus
from app.main import app
from app.models import ReportRun


def _snapshot(run_id: str, report_md: str | None) -> ReportRun:
    return ReportRun(
        id=run_id,
        topic="PDF testing",
        status="completed" if report_md else "running",
        report_md=report_md,
        created_at=datetime.now(UTC),
    )


def test_report_pdf_generates_once_and_serves_cached_content(monkeypatch, tmp_path) -> None:
    snapshot = _snapshot("pdf-cache-test", "# Cached report\n\nA finding [1].")
    app.state.event_bus = EventBus()
    app.state.event_bus.restore(snapshot)
    app.state.settings = Settings(runs_dir=str(tmp_path))
    calls: list[str] = []

    def fake_render(report_md: str) -> bytes:
        calls.append(report_md)
        return b"%PDF-cached"

    monkeypatch.setattr(reports, "render_pdf", fake_render)

    with TestClient(app) as client:
        first = client.get("/api/reports/pdf-cache-test/report.pdf")
        second = client.get("/api/reports/pdf-cache-test/report.pdf")

    assert first.status_code == 200
    assert first.headers["content-type"] == "application/pdf"
    assert "pdf-cache-test.pdf" in first.headers["content-disposition"]
    assert first.content == b"%PDF-cached"
    assert second.content == first.content
    assert calls == [snapshot.report_md]
    assert (tmp_path / "pdf-cache-test.pdf").read_bytes() == b"%PDF-cached"


def test_report_pdf_requires_a_ready_report(monkeypatch, tmp_path) -> None:
    snapshot = _snapshot("pdf-not-ready", None)
    app.state.event_bus = EventBus()
    app.state.event_bus.restore(snapshot)
    app.state.settings = Settings(runs_dir=str(tmp_path))
    monkeypatch.setattr(reports, "render_pdf", lambda _report_md: pytest.fail("must not render"))

    with TestClient(app) as client:
        response = client.get("/api/reports/pdf-not-ready/report.pdf")

    assert response.status_code == 409
    assert response.json() == {"detail": "Report is not ready"}
    assert not (tmp_path / "pdf-not-ready.pdf").exists()


def test_pdf_cache_rejects_unsafe_snapshot_ids(tmp_path) -> None:
    snapshot = _snapshot("../outside", "# Report")

    with pytest.raises(ValueError, match="safe"):
        reports._pdf_cache_path(snapshot, tmp_path)
