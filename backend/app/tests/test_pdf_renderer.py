"""Focused tests for report PDF HTML and WeasyPrint integration."""

import re

import pytest

from app.pdf import renderer


def test_build_html_includes_report_layout_and_linked_citations() -> None:
    long_url = "https://example.com/research/" + ("very-long-path/" * 10)
    markdown = (
        "# Research report\n\n"
        "## Findings\n\n"
        "A claim supported by [1].\n\n"
        "A note[^note].\n\n"
        "[^note]: A deterministic footnote.\n\n"
        "| Metric | Value |\n| --- | --- |\n| Coverage | 95% |\n\n"
        "## Sources\n\n"
        f"**[1] Source title** — [{long_url}]({long_url})\n"
    )

    document = renderer.build_html(markdown)

    assert 'size: A4' in document
    assert 'content: "Page " counter(page) " of " counter(pages)' in document
    assert 'break-after: avoid' in document
    assert '<sup class="citation"><a href="#source-1">[1]</a></sup>' in document
    assert '<a id="source-1" class="source-anchor"></a>' in document
    assert 'class="source-url"' in document
    assert f'href="{long_url}"' in document
    assert renderer._truncate_url(long_url) in document
    assert "<table>" in document
    assert "A deterministic footnote." in document


def test_render_pdf_passes_wrapped_html_to_weasyprint(monkeypatch) -> None:
    captured: dict[str, str] = {}

    class FakeHTML:
        def __init__(self, *, string: str) -> None:
            captured["html"] = string

        def write_pdf(self) -> bytes:
            return b"%PDF-test"

    monkeypatch.setattr(renderer, "HTML", FakeHTML)

    assert renderer.render_pdf("# Offline report") == b"%PDF-test"
    assert captured["html"].startswith("<!doctype html>")
    assert "Offline report" in captured["html"]


def test_render_pdf_can_use_local_converter_fallback(monkeypatch) -> None:
    monkeypatch.setattr(renderer, "HTML", None)
    monkeypatch.setattr(renderer, "_render_with_libreoffice", lambda _markdown: b"%PDF-fallback")

    assert renderer.render_pdf("# Local fallback") == b"%PDF-fallback"


def test_mock_report_pdf_has_sources_and_multiple_pages() -> None:
    markdown = (
        "# Mock research report\n\n"
        + "\n\n".join(
            f"## Finding {index}\n\n"
            + ("This deterministic mock finding supports the report with evidence [1]. " * 14)
            for index in range(36)
        )
        + "\n\n## Sources\n\n**[1] Mock source** — [https://example.com](https://example.com)\n"
    )

    assert "Sources" in renderer.build_html(markdown)
    try:
        pdf = renderer.render_pdf(markdown)
    except RuntimeError as exc:
        pytest.skip(str(exc))

    page_objects = re.findall(rb"/Type\s*/Page(?!s)", pdf)
    assert len(page_objects) > 2
