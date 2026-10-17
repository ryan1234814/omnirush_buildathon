"""Tests for the Phase 1 health endpoint."""

from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app


def test_health_without_provider_keys(monkeypatch: object) -> None:
    """Missing credentials should be reported, not treated as an app failure."""

    for variable in ("OPENAI_API_KEY", "TAVILY_API_KEY", "SERPER_API_KEY"):
        monkeypatch.setenv(variable, "")  # type: ignore[attr-defined]
    monkeypatch.setenv("SEARCH_PROVIDER", "tavily")  # type: ignore[attr-defined]
    monkeypatch.setenv("MOCK_MODE", "false")  # type: ignore[attr-defined]

    app.dependency_overrides[get_settings] = lambda: Settings(
        openai_api_key=None,
        tavily_api_key=None,
        search_provider="tavily",
        mock_mode=False,
    )
    try:
        response = TestClient(app).get("/api/health")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "search_provider": "tavily",
        "search_configured": False,
        "llm_configured": False,
        "mock_mode": False,
    }
