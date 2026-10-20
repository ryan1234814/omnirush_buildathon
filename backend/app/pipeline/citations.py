"""Citation registry construction and strict report citation validation."""

from __future__ import annotations

import re
from collections.abc import Sequence
from math import ceil

from app.models import SourceEntry, SourceRegistry
from app.pipeline.extract import Source

_CITATION_RE = re.compile(r"(?:\[(\d+)\]|【(\d+)】)")
_WORDS_PER_TOKEN = 0.75
_MAX_EXCERPT_WORDS = 1500
_DEFAULT_CONTEXT_TOKENS = 24_000


def _clean_words(text: str) -> list[str]:
    """Normalize whitespace and split text into words."""

    return re.sub(r"\s+", " ", text).strip().split()


def _estimate_tokens(text: str) -> int:
    """Use a conservative word-based token estimate without a tokenizer dependency."""

    return ceil(len(_clean_words(text)) / _WORDS_PER_TOKEN)


def estimate_tokens(text: str) -> int:
    """Public word-based token estimate used for run telemetry payloads."""

    return _estimate_tokens(text)


def build_registry(
    sources: Sequence[Source],
    *,
    max_excerpt_words: int = _MAX_EXCERPT_WORDS,
    max_context_tokens: int = _DEFAULT_CONTEXT_TOKENS,
) -> SourceRegistry:
    """Assign stable IDs and retain highest-ranked excerpts within the context budget."""

    if max_excerpt_words < 1 or max_context_tokens < 1:
        return SourceRegistry()

    ordered_sources = sorted(sources, key=lambda source: -source.rank_score)
    entries: list[SourceEntry] = []
    remaining_tokens = min(max_context_tokens, _DEFAULT_CONTEXT_TOKENS)
    for source in ordered_sources:
        words = _clean_words(source.content)[:max_excerpt_words]
        available_words = min(len(words), int(remaining_tokens * _WORDS_PER_TOKEN))
        if available_words < 1:
            break
        excerpt = " ".join(words[:available_words])
        entry = SourceEntry(
            id=len(entries) + 1,
            url=source.url,
            title=source.title,
            excerpt=excerpt,
        )
        entries.append(entry)
        remaining_tokens -= _estimate_tokens(excerpt)
        if remaining_tokens <= 0:
            break

    used_tokens = sum(_estimate_tokens(entry.excerpt) for entry in entries)
    return SourceRegistry(entries=entries, context_token_estimate=used_tokens)


def count_citations(md: str) -> int:
    """Count every inline ``[n]`` citation marker remaining in a validated report."""

    return len(_CITATION_RE.findall(md))


def validate_report(md: str, registry: SourceRegistry) -> tuple[str, list[int]]:
    """Remove citations that do not point to an entry in ``registry``."""

    valid_ids = {entry.id for entry in registry.entries}
    removed: list[int] = []

    def replace(match: re.Match[str]) -> str:
        citation_id = int(match.group(1) or match.group(2))
        if citation_id in valid_ids:
            return f"[{citation_id}]"
        removed.append(citation_id)
        return ""

    return _CITATION_RE.sub(replace, md), removed
