"""Report diff and multi-format export endpoints."""

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.config import Settings
from app.events.bus import EventBus
from app.main import app
from app.models import ReportRun, SourceEntry


def _run(
    run_id: str,
    report_md: str,
    sources: list[SourceEntry],
    *,
    partial: bool = False,
) -> ReportRun:
    return ReportRun(
        id=run_id,
        topic="quantum computing 2026",
        created_at=datetime.now(UTC),
        status="completed",
        stage="DONE",
        outcome="partial" if partial else "completed",
        partial=partial,
        report_md=report_md,
        sources=sources,
    )


def _client(monkeypatch, tmp_path, runs: list[ReportRun]) -> TestClient:
    bus = EventBus()
    for run in runs:
        bus.restore(run)
    settings = Settings(mock_mode=True, search_provider="mock", runs_dir=str(tmp_path))
    monkeypatch.setattr(app.state, "event_bus", bus)
    monkeypatch.setattr(app.state, "settings", settings)
    monkeypatch.setattr(app.state, "report_tasks", set())
    return TestClient(app)


_PREVIOUS = (
    "# Research report: quantum computing 2026\n\n"
    "## Executive summary\n\nOld headline claim [1].\n\n"
    "## Findings\n\nStable finding [1].\n\n"
    "## Dropped section\n\nThis section disappeared.\n\n"
    "## Sources\n\n1. https://one.test\n"
)
_CURRENT = (
    "# Research report: quantum computing 2026\n\n"
    "## Executive summary\n\nUpdated headline claim [1][2].\n\n"
    "## Findings\n\nStable finding [1].\n\n"
    "## New section\n\nFresh evidence [2].\n\n"
    "## Sources\n\n1. https://one.test\n2. https://two.test\n"
)
_SOURCES_OLD = [SourceEntry(id=1, url="https://one.test", title="One", excerpt="Evidence one.")]
_SOURCES_NEW = [
    *_SOURCES_OLD,
    SourceEntry(id=2, url="https://two.test", title="Two", excerpt="Evidence two."),
]


def test_diff_reports_section_level_changes(monkeypatch, tmp_path) -> None:
    client = _client(
        monkeypatch,
        tmp_path,
        [
            # The path run is the report being viewed (newer); the compared run is older.
            _run("base-run", _CURRENT, _SOURCES_NEW),
            _run("compare-run", _PREVIOUS, _SOURCES_OLD),
        ],
    )

    response = client.get("/api/reports/base-run/diff?compare_run_id=compare-run")

    assert response.status_code == 200
    payload = response.json()
    assert payload["base_run_id"] == "base-run"
    assert payload["compare_run_id"] == "compare-run"
    assert "section change(s) detected" in payload["summary"]
    statuses = {change["section"]: change["status"] for change in payload["changes"]}
    assert statuses["Executive summary"] == "changed"
    assert statuses["New section"] == "added"
    assert statuses["Dropped section"] == "removed"
    assert statuses["Sources"] == "changed"
    assert "Findings" not in statuses
    changed = next(
        change for change in payload["changes"] if change["section"] == "Executive summary"
    )
    assert "Old headline" in changed["before"]
    assert "Updated headline" in changed["after"]
    assert payload["source_removals"] == []
    assert payload["source_additions"][0]["url"] == "https://two.test"


def test_diff_errors(monkeypatch, tmp_path) -> None:
    queued = _run("queued-run", "", [])
    queued.status = "running"
    queued.report_md = None
    client = _client(
        monkeypatch,
        tmp_path,
        [_run("base-run", _CURRENT, _SOURCES_NEW), queued],
    )

    assert client.get("/api/reports/nope/diff?compare_run_id=base-run").status_code == 404
    assert client.get("/api/reports/base-run/diff?compare_run_id=nope").status_code == 404
    assert (
        client.get("/api/reports/base-run/diff?compare_run_id=queued-run").status_code == 409
    )


def test_multi_format_exports(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path, [_run("base-run", _CURRENT, _SOURCES_NEW)])

    html = client.get("/api/reports/base-run/report.html")
    assert html.status_code == 200
    assert html.headers["content-type"].startswith("text/html")
    assert "<h2" in html.text

    text = client.get("/api/reports/base-run/report.txt")
    assert text.status_code == 200
    assert "#" not in text.text.splitlines()[0]
    assert "[2]" not in text.text

    payload = client.get("/api/reports/base-run/report.json")
    assert payload.status_code == 200
    body = payload.json()
    assert body["topic"] == "quantum computing 2026"
    assert len(body["sources"]) == 2
    assert body["report_md"] == _CURRENT

    for kind, marker in (
        ("executive", "# Executive summary"),
        ("blog", "# Research briefing"),
        ("linkedin", "# LinkedIn digest"),
        ("marp", "marp: true"),
    ):
        response = client.get(f"/api/reports/base-run/report/{kind}")
        assert response.status_code == 200
        assert response.text.startswith(marker) or marker in response.text
        assert "attachment" in response.headers["content-disposition"]

    assert client.get("/api/reports/base-run/report/novel").status_code == 404


def test_formats_guard_errors(monkeypatch, tmp_path) -> None:
    partial = _run("partial-run", _CURRENT, _SOURCES_NEW, partial=True)
    queued = _run("queued-run", "", [])
    queued.status = "running"
    queued.report_md = None
    client = _client(monkeypatch, tmp_path, [partial, queued])

    for path in ("report.html", "report.txt", "report.json", "report/blog"):
        assert client.get(f"/api/reports/queued-run/{path}").status_code == 409
        assert client.get(f"/api/reports/partial-run/{path}").status_code == 409
    assert client.get("/api/reports/missing/report.html").status_code == 404
