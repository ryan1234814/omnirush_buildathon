"""Citation registry and validation tests."""

from app.models import SourceRegistry
from app.pipeline.citations import build_registry, validate_report
from app.pipeline.extract import Source


def source(index: int, content: str) -> Source:
    return Source(
        title=f"Source {index}",
        url=f"https://example.com/{index}",
        content=content,
        search_relevance=1.0 - index / 100,
    )


def test_registry_assigns_ids_and_caps_excerpts() -> None:
    registry = build_registry([source(1, "word " * 2000)], max_excerpt_words=1500)

    assert registry.entries[0].id == 1
    assert len(registry.entries[0].excerpt.split()) == 1500
    assert registry.context_token_estimate <= 2000


def test_registry_trims_lowest_ranked_sources_first() -> None:
    registry = build_registry(
        [source(1, "top " * 50), source(2, "lower " * 50)],
        max_excerpt_words=1500,
        max_context_tokens=70,
    )

    assert registry.entries[0].excerpt == " ".join(["top"] * 50)
    assert len(registry.entries) == 2
    assert len(registry.entries[1].excerpt.split()) < 50


def test_invalid_citations_are_removed_and_valid_ones_unchanged() -> None:
    registry = SourceRegistry(
        entries=[
            {"id": 1, "url": "https://one.test", "title": "One", "excerpt": "one"},
            {"id": 2, "url": "https://two.test", "title": "Two", "excerpt": "two"},
        ]
    )

    cleaned, removed = validate_report("Claim [1]. Fabricated [7]. Also 【2】.", registry)

    assert cleaned == "Claim [1]. Fabricated . Also [2]."
    assert removed == [7]
