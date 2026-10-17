"""Tests for URL deduplication and source ranking."""

from app.pipeline.extract import Source
from app.pipeline.ranker import normalize_url, rank_sources


def source(url: str, content: str, relevance: float = 0.8) -> Source:
    return Source(
        title="Test source",
        url=url,
        content=content,
        search_relevance=relevance,
        has_title=True,
    )


def test_normalize_url_drops_query_tracking_and_trailing_slash() -> None:
    assert normalize_url("HTTPS://Example.com/article/?utm_source=test&ref=home") == (
        "https://example.com/article"
    )


def test_ranker_deduplicates_url_variants() -> None:
    long_content = "Useful research content. " * 150
    ranked = rank_sources(
        [
            source("https://example.com/article?utm_source=one", long_content, 0.7),
            source("https://example.com/article?utm_campaign=two", long_content, 0.95),
        ],
        top_k=6,
    )

    assert len(ranked) == 1
    assert ranked[0].search_relevance == 0.95
    assert ranked[0].normalized_url == "https://example.com/article"


def test_ranker_penalizes_short_content() -> None:
    ranked = rank_sources(
        [
            source("https://example.com/short", "Too short."),
            source("https://example.com/long", "Detailed source content. " * 150),
        ]
    )

    assert ranked[0].url == "https://example.com/long"
    assert ranked[0].quality_score > ranked[1].quality_score


def test_ranker_empty_input_and_top_k() -> None:
    assert rank_sources([]) == []
    assert (
        len(
            rank_sources(
                [source(f"https://example.com/{index}", "content" * 100) for index in range(4)],
                top_k=2,
            )
        )
        == 2
    )
