"""Streaming citation-strict synthesis with an offline mock path."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from openai import AsyncOpenAI

from app.models import SourceRegistry
from app.prompts.synthesis import (
    SYNTHESIS_SYSTEM_PROMPT,
    build_synthesis_user_prompt,
    format_excerpts,
)


def _mock_sentence(excerpt: str) -> str:
    """Turn a bounded excerpt into a short deterministic mock claim."""

    sentence = excerpt.split(". ", 1)[0].strip().rstrip(".")
    return sentence or "The available source excerpt contains no usable claim"


async def stream_report(
    topic: str,
    registry: SourceRegistry,
    *,
    client: AsyncOpenAI | Any | None = None,
    model: str = "",
    mock_mode: bool = False,
) -> AsyncIterator[str]:
    """Yield report text chunks from the LLM or deterministic mock synthesizer."""

    if mock_mode:
        if registry.entries:
            summary = f"Research on **{topic}** is summarized from the supplied excerpts [1]."
        else:
            summary = f"Research on **{topic}** lacks source support. *(unverified)*"
        chunks = [f"## Executive summary\n\n{summary}\n"]
        for entry in registry.entries:
            chunks.append(
                f"\n## Finding {entry.id}\n\n{_mock_sentence(entry.excerpt)} [{entry.id}]\n"
            )
        if not registry.entries:
            chunks.append(
                "\n## Findings\n\nNo source-backed findings were available. *(unverified)*\n"
            )
        for chunk in chunks:
            yield chunk
        return

    if client is None or not model:
        raise RuntimeError("LLM synthesis is not configured")
    request = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYNTHESIS_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": build_synthesis_user_prompt(
                    topic,
                    format_excerpts(registry.entries),
                ),
            },
        ],
        "stream": True,
        "timeout": 60.0,
    }
    response = None
    for attempt in range(2):
        try:
            response = await client.chat.completions.create(**request)
            break
        except Exception as exc:
            if attempt == 1 or getattr(exc, "status_code", None) != 429:
                raise
            await asyncio.sleep(20.0)
    if response is None:
        raise RuntimeError("LLM synthesis did not return a stream")
    async for chunk in response:
        choices = getattr(chunk, "choices", None) or []
        if not choices:
            continue
        content = getattr(getattr(choices[0], "delta", None), "content", None)
        if content:
            yield content
