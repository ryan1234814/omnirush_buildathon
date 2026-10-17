"""Tests for the Phase 1 health endpoint."""

from fastapi.testclient import TestClient

from app.main import app


def test_health_without_provider_keys(monkeypatch: object) -> None:
    """Missing credentials should be reported, not treated as an app failure."""

    for variable in ("OPENAI_API_KEY", "TAVILY_API_KEY", "SERPER_API_KEY"):
        monkeypatch.delenv(variable, raising=False)  # type: ignore[attr-defined]

    response = TestClient(app).get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "search_provider": "tavily",
        "search_configured": False,
        "llm_configured": False,
        "mock_mode": False,
    }
