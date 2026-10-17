"""Offline smoke coverage for the throwaway integration script."""

from __future__ import annotations

import pytest

from app.config import Settings
from scripts.integration_check import _extract_clean_text, run_check


@pytest.mark.asyncio
async def test_mock_integration_check_prints_plan_results_and_fixture_text(
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = Settings(search_provider="mock", mock_mode=True)

    assert await run_check("quantum computing", 1, settings) == 0

    output = capsys.readouterr().out
    assert "Planned sub-queries:" in output
    assert "Search results:" in output
    assert "Extracted sources:" in output
    assert "Ranked sources" in output
    assert "Extracted text preview" in output


def test_extract_clean_text_uses_tavily_raw_content() -> None:
    assert _extract_clean_text({"results": [{"raw_content": "  cleaned text  "}]}) == "cleaned text"


def test_extract_clean_text_rejects_empty_payload() -> None:
    with pytest.raises(Exception, match="no cleaned extract text"):
        _extract_clean_text({"results": [{"url": "https://example.com"}]})
