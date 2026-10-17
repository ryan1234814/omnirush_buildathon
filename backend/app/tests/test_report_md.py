"""Deterministic Markdown report assembly tests."""

from app.models import SourceRegistry
from app.pipeline.report_md import assemble


def test_assemble_generates_registry_references_exactly() -> None:
    registry = SourceRegistry(
        entries=[
            {
                "id": 1,
                "url": "https://one.test/article",
                "title": "One",
                "excerpt": "one excerpt",
            },
            {
                "id": 2,
                "url": "https://two.test/article",
                "title": "Two",
                "excerpt": "two excerpt",
            },
        ]
    )

    report = assemble(
        "A topic",
        "## Findings\n\nClaim [1].\n\n## Sources\nModel invented source",
        registry,
    )

    assert "Model invented source" not in report
    assert "**[1] One** — [https://one.test/article](https://one.test/article)" in report
    assert "**[2] Two** — [https://two.test/article](https://two.test/article)" in report
    assert report.count("## Sources") == 1
