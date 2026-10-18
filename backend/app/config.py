"""Application configuration loaded from environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the API and its external providers."""

    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    tavily_api_key: str | None = None
    serper_api_key: str | None = None
    search_provider: Literal["tavily", "serper", "mock"] = "tavily"
    mock_mode: bool = False
    top_k: int = Field(default=6, ge=1)
    synthesis_context_tokens: int = Field(default=3_000, ge=500)
    max_search_calls: int = Field(default=8, ge=1)
    search_retry_backoff_seconds: float = Field(default=0.25, ge=0, le=5)
    planning_budget_seconds: float = Field(default=8.0, gt=0)
    search_budget_seconds: float = Field(default=5.0, gt=0)
    extraction_budget_seconds: float = Field(default=25.0, gt=0)
    synthesis_budget_seconds: float = Field(default=45.0, gt=0)
    total_budget_seconds: float = Field(default=85.0, gt=0)
    runs_dir: str = "data/runs"

    model_config = SettingsConfigDict(
        # The documented .env lives at the repository root, while backend commands run from here.
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def llm_configured(self) -> bool:
        """Return whether the LLM has the credentials needed to be called."""

        return bool(self.openai_api_key and self.llm_model)

    @property
    def search_configured(self) -> bool:
        """Return whether the selected search provider can be called."""

        if self.mock_mode or self.search_provider == "mock":
            return True
        if self.search_provider == "tavily":
            return bool(self.tavily_api_key)
        return bool(self.serper_api_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return one cached settings instance for the process."""

    return Settings()
