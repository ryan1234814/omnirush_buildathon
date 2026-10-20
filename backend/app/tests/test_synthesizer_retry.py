"""Tests for transient-error retry in the real (non-mock) synthesis path."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.models import SourceRegistry
from app.pipeline.synthesizer import stream_report


class _StatusError(Exception):
    """Stand-in for an openai APIStatusError carrying an HTTP status code."""

    def __init__(self, status_code: int) -> None:
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code


async def _fake_stream(chunks: list[str]):
    for content in chunks:
        yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=content))])


class _FakeCompletions:
    def __init__(self, fail_statuses: list[int], succeed_chunks: list[str]) -> None:
        self._fail_statuses = list(fail_statuses)
        self._succeed_chunks = succeed_chunks
        self.calls = 0

    async def create(self, **_kwargs):
        self.calls += 1
        if self._fail_statuses:
            raise _StatusError(self._fail_statuses.pop(0))
        return _fake_stream(self._succeed_chunks)


class _FakeClient:
    def __init__(self, fail_statuses: list[int], succeed_chunks: list[str]) -> None:
        self.chat = SimpleNamespace(completions=_FakeCompletions(fail_statuses, succeed_chunks))


@pytest.mark.asyncio
async def test_transient_5xx_is_retried_then_succeeds(monkeypatch) -> None:
    # Keep the test fast: collapse the backoff sleeps.
    async def _no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr("app.pipeline.synthesizer.asyncio.sleep", _no_sleep)
    client = _FakeClient(fail_statuses=[503], succeed_chunks=["## Summary\n", "finding [1]\n"])
    registry = SourceRegistry()

    text = "".join(
        [
            chunk
            async for chunk in stream_report(
                "topic", registry, client=client, model="test-model", mock_mode=False
            )
        ]
    )

    assert text == "## Summary\nfinding [1]\n"
    assert client.chat.completions.calls == 2  # one transient failure, one success


@pytest.mark.asyncio
async def test_non_transient_error_is_raised(monkeypatch) -> None:
    async def _no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr("app.pipeline.synthesizer.asyncio.sleep", _no_sleep)
    client = _FakeClient(fail_statuses=[400], succeed_chunks=["unused"])
    registry = SourceRegistry()

    with pytest.raises(_StatusError):
        [
            chunk
            async for chunk in stream_report(
                "topic", registry, client=client, model="test-model", mock_mode=False
            )
        ]

    assert client.chat.completions.calls == 1  # 400 is not retried
