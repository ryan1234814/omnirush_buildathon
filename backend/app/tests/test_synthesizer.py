"""Streaming synthesis tests."""

from types import SimpleNamespace

import pytest

from app.models import SourceRegistry
from app.pipeline.synthesizer import stream_report


class FakeCompletions:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def create(self, **kwargs: object):
        self.calls.append(kwargs)

        async def stream():
            yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="## A"))])
            yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=None))])
            yield SimpleNamespace(choices=[])
            yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=" [1]"))])

        return stream()


@pytest.mark.asyncio
async def test_stream_report_forwards_streaming_request_and_skips_empty_deltas() -> None:
    completions = FakeCompletions()
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    registry = SourceRegistry(
        entries=[
            {
                "id": 1,
                "url": "https://one.test",
                "title": "One",
                "excerpt": "A source-backed claim.",
            }
        ]
    )

    chunks = [
        chunk
        async for chunk in stream_report(
            "topic",
            registry,
            client=client,
            model="test-model",
        )
    ]

    assert chunks == ["## A", " [1]"]
    assert completions.calls[0]["stream"] is True
    assert completions.calls[0]["model"] == "test-model"


@pytest.mark.asyncio
async def test_mock_synthesis_is_offline_and_citation_valid() -> None:
    registry = SourceRegistry(
        entries=[
            {
                "id": 1,
                "url": "https://one.test",
                "title": "One",
                "excerpt": "The source says this is important.",
            }
        ]
    )

    chunks = [chunk async for chunk in stream_report("topic", registry, mock_mode=True)]

    assert "[1]" in "".join(chunks)
