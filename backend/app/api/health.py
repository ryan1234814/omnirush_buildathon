"""Health and configuration-status endpoints."""

from fastapi import APIRouter, Depends

from app.config import Settings, get_settings

router = APIRouter(tags=["health"])


@router.get("/api/health")
async def health(settings: Settings = Depends(get_settings)) -> dict[str, bool | str]:
    """Report service availability without exposing credentials."""

    return {
        "status": "ok",
        "search_provider": settings.search_provider,
        "search_configured": settings.search_configured,
        "llm_configured": settings.llm_configured,
        "mock_mode": settings.mock_mode,
    }
