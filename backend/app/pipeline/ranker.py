"""URL normalization, source deduplication, and deterministic ranking."""

from __future__ import annotations

import math
from collections.abc import Sequence
from urllib.parse import urlsplit, urlunsplit

from app.pipeline.extract import Source


def normalize_url(url: str) -> str:
    """Normalize URLs for deduplication by dropping query and tracking data."""

    parsed = urlsplit(url.strip())
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    if netloc.endswith(":80") and scheme == "http":
        netloc = netloc[:-3]
    if netloc.endswith(":443") and scheme == "https":
        netloc = netloc[:-4]
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((scheme, netloc, path, "", ""))


def _length_score(content: str) -> float:
    """Give short extracts a clear penalty while diminishing returns for long text."""

    length = len(content.strip())
    if length == 0:
        return 0.0
    return min(1.0, math.log1p(length) / math.log1p(4000))


def quality_score(source: Source) -> float:
    """Combine length, extraction score, and useful metadata flags."""

    length = _length_score(source.content)
    metadata = sum((source.has_title, source.has_author, source.has_date)) / 3
    extraction = max(0.0, min(1.0, source.trafilatura_score))
    return 0.65 * length + 0.2 * extraction + 0.15 * metadata


def _ranked(source: Source, normalized_url: str) -> Source:
    """Attach reproducible quality and combined scores to a source."""

    quality = quality_score(source)
    relevance = max(0.0, min(1.0, source.search_relevance))
    return Source(
        title=source.title,
        url=source.url,
        content=source.content,
        search_relevance=source.search_relevance,
        extraction_method=source.extraction_method,
        trafilatura_score=source.trafilatura_score,
        has_title=source.has_title,
        has_author=source.has_author,
        has_date=source.has_date,
        normalized_url=normalized_url,
        quality_score=quality,
        rank_score=0.6 * relevance + 0.4 * quality,
    )


def rank_sources(sources: Sequence[Source], top_k: int = 6) -> list[Source]:
    """Deduplicate sources, score them, and return the best ``top_k``."""

    if top_k < 1:
        return []
    best_by_url: dict[str, Source] = {}
    for source in sources:
        normalized_url = normalize_url(source.url)
        ranked = _ranked(source, normalized_url)
        current = best_by_url.get(normalized_url)
        if current is None or ranked.rank_score > current.rank_score:
            best_by_url[normalized_url] = ranked
    return sorted(
        best_by_url.values(),
        key=lambda source: (-source.rank_score, source.normalized_url or source.url),
    )[:top_k]
