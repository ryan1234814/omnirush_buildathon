"""Render report Markdown as a styled, citation-linked PDF."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import markdown

# WeasyPrint needs native libraries that are supplied by the container image. Keeping this
# import lazy also allows Markdown/template tests to run on developer machines without them.
HTML: Any = None


REPORT_CSS = """
@page {
  size: A4;
  margin: 18mm 17mm 20mm;

  @bottom-right {
    color: #64748b;
    content: "Page " counter(page) " of " counter(pages);
    font-size: 8pt;
  }
}

* {
  box-sizing: border-box;
}

body {
  color: #1e293b;
  font-family: "DejaVu Sans", sans-serif;
  font-size: 10.5pt;
  line-height: 1.55;
}

h1,
h2,
h3,
h4 {
  color: #0f172a;
  line-height: 1.2;
  break-after: avoid;
  page-break-after: avoid;
}

h1 {
  border-bottom: 2px solid #cbd5e1;
  font-size: 23pt;
  margin: 0 0 18pt;
  padding-bottom: 8pt;
}

h2 {
  border-bottom: 1px solid #e2e8f0;
  font-size: 15pt;
  margin: 20pt 0 8pt;
  padding-bottom: 3pt;
}

h3 {
  font-size: 12pt;
  margin: 15pt 0 5pt;
}

p,
ul,
ol,
table,
blockquote {
  orphans: 3;
  widows: 3;
}

table {
  border-collapse: collapse;
  break-inside: avoid;
  font-size: 9pt;
  margin: 10pt 0;
  width: 100%;
}

th,
td {
  border: 1px solid #cbd5e1;
  padding: 5pt 6pt;
  vertical-align: top;
}

th {
  background: #f1f5f9;
  color: #0f172a;
}

blockquote {
  border-left: 3px solid #94a3b8;
  color: #475569;
  margin-left: 0;
  padding-left: 10pt;
}

code {
  background: #f1f5f9;
  font-family: "DejaVu Sans Mono", monospace;
  padding: 1pt 3pt;
}

a {
  color: #0369a1;
}

.citation {
  font-size: 7.5pt;
  line-height: 0;
  vertical-align: super;
}

.citation a {
  text-decoration: none;
}

.source-anchor {
  display: inline-block;
  height: 0;
  width: 0;
}

.source-url {
  display: inline-block;
  max-width: 125mm;
  overflow: hidden;
  text-overflow: ellipsis;
  vertical-align: bottom;
  white-space: nowrap;
}

.footnote {
  border-top: 1px solid #e2e8f0;
  font-size: 9pt;
  margin-top: 14pt;
  padding-top: 6pt;
}
"""

_CITATION_RE = re.compile(r"(?<![\w\]])\[(\d{1,3})\](?!\()")
_SOURCE_ENTRY_RE = re.compile(r"^\[(\d{1,3})\]")
_URL_RE = re.compile(r"^https?://", re.IGNORECASE)


def _truncate_url(url: str, limit: int = 96) -> str:
    """Keep source links readable while retaining the full URL in the href."""

    if len(url) <= limit:
        return url
    return f"{url[: limit - 1]}…"


class _ReportHTMLParser(HTMLParser):
    """Add citation/source anchors without changing Markdown's generated structure."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.parts: list[str] = []
        self._tag_stack: list[str] = []
        self._heading_text: list[str] | None = None
        self._in_sources = False
        self._in_source_paragraph = False
        self._source_anchor_added = False
        self._source_url: str | None = None

    def _in_tag(self, tag: str) -> bool:
        return tag in self._tag_stack

    def _serialize_start_tag(self, tag: str, attrs: list[tuple[str, str | None]]) -> str:
        rendered_attrs = []
        for name, value in attrs:
            if value is None:
                rendered_attrs.append(name)
            else:
                rendered_attrs.append(f'{name}="{escape(value, quote=True)}"')
        suffix = f" {' '.join(rendered_attrs)}" if rendered_attrs else ""
        return f"<{tag}{suffix}>"

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"h2", "h3"}:
            self._heading_text = []
        if tag == "p" and self._in_sources:
            self._in_source_paragraph = True
            self._source_anchor_added = False

        attrs = list(attrs)
        href = next((value for name, value in attrs if name == "href"), None)
        if tag == "a" and self._in_sources and href and _URL_RE.match(href):
            attrs.append(("class", "source-url"))
            attrs.append(("title", href))
            self._source_url = href
            self.parts.append(self._serialize_start_tag(tag, attrs))
            self.parts.append(escape(_truncate_url(href)))
            self._tag_stack.append(tag)
            return

        self.parts.append(self._serialize_start_tag(tag, attrs))
        self._tag_stack.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.parts.append(self._serialize_start_tag(tag, list(attrs)).replace(">", " />", 1))

    def handle_endtag(self, tag: str) -> None:
        self.parts.append(f"</{tag}>")
        if self._tag_stack:
            self._tag_stack.pop()
        if tag == "a":
            self._source_url = None
        if tag == "p":
            self._in_source_paragraph = False
            self._source_anchor_added = False
        if tag in {"h2", "h3"} and self._heading_text is not None:
            heading = "".join(self._heading_text).strip().casefold()
            self._in_sources = heading == "sources"
            self._heading_text = None

    def handle_data(self, data: str) -> None:
        if self._heading_text is not None:
            self._heading_text.append(data)

        if (
            self._in_sources
            and self._in_source_paragraph
            and not self._source_anchor_added
        ):
            source_match = _SOURCE_ENTRY_RE.match(data.strip())
            if source_match:
                source_id = source_match.group(1)
                self.parts.append(f'<a id="source-{source_id}" class="source-anchor"></a>')
                self._source_anchor_added = True

        if self._source_url is not None:
            return

        if not self._in_sources and not self._in_tag("a") and not self._in_tag("code"):
            cursor = 0
            for match in _CITATION_RE.finditer(data):
                self.parts.append(escape(data[cursor : match.start()]))
                source_id = match.group(1)
                self.parts.append(
                    f'<sup class="citation"><a href="#source-{source_id}">[{source_id}]</a></sup>'
                )
                cursor = match.end()
            self.parts.append(escape(data[cursor:]))
            return

        self.parts.append(escape(data))

    def handle_entityref(self, name: str) -> None:
        if self._source_url is not None:
            return
        self.parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if self._source_url is not None:
            return
        self.parts.append(f"&#{name};")

    def handle_comment(self, data: str) -> None:
        self.parts.append(f"<!--{data}-->")

    def handle_decl(self, decl: str) -> None:
        self.parts.append(f"<!{decl}>")

    def handle_pi(self, data: str) -> None:
        self.parts.append(f"<?{data}>")

    def html(self) -> str:
        """Return the transformed HTML fragment."""

        return "".join(self.parts)


def markdown_to_html(md: str) -> str:
    """Convert report Markdown into citation-aware HTML."""

    rendered = markdown.markdown(md, extensions=["tables", "footnotes"])
    parser = _ReportHTMLParser()
    parser.feed(rendered)
    parser.close()
    return parser.html()


def build_html(md: str) -> str:
    """Wrap report HTML in the standalone document consumed by WeasyPrint."""

    body = markdown_to_html(md)
    return (
        "<!doctype html>"
        '<html lang="en"><head><meta charset="utf-8">'
        "<title>Research report</title>"
        f"<style>{REPORT_CSS}</style>"
        f'</head><body><main class="report">{body}</main></body></html>'
    )


def _render_with_libreoffice(md: str) -> bytes:
    """Provide a macOS developer fallback when WeasyPrint native libraries are absent.

    Docker and production use WeasyPrint. LibreOffice is only an optional host fallback so a
    developer can exercise the complete download flow without installing global Pango/GObject
    libraries. The same generated HTML and embedded report stylesheet are passed to the converter.
    """

    executable = shutil.which("soffice") or shutil.which("libreoffice")
    if executable is None:
        raise RuntimeError(
            "WeasyPrint is unavailable. Run the backend container or install WeasyPrint's "
            "native libraries; LibreOffice was not found for the local fallback."
        )

    with tempfile.TemporaryDirectory(prefix="omnirush-pdf-") as directory:
        workdir = Path(directory)
        html_path = workdir / "report.html"
        pdf_path = workdir / "report.pdf"
        html_path.write_text(build_html(md), encoding="utf-8")
        profile = (workdir / "profile").as_uri()
        result = subprocess.run(
            [
                executable,
                "--headless",
                f"-env:UserInstallation={profile}",
                "--convert-to",
                "pdf",
                "--outdir",
                str(workdir),
                str(html_path),
            ],
            capture_output=True,
            check=False,
            text=True,
            timeout=60,
        )
        if result.returncode != 0 or not pdf_path.is_file():
            detail = (result.stderr or result.stdout).strip()
            suffix = f": {detail}" if detail else ""
            raise RuntimeError(f"LibreOffice could not render the report PDF{suffix}")
        return pdf_path.read_bytes()


def render_pdf(md: str) -> bytes:
    """Render report Markdown to PDF bytes with WeasyPrint."""

    global HTML
    if HTML is None:
        try:
            from weasyprint import HTML as WeasyPrintHTML
        except (ImportError, OSError) as exc:  # pragma: no cover - platform setup
            try:
                return _render_with_libreoffice(md)
            except RuntimeError as fallback_exc:
                raise RuntimeError(str(fallback_exc)) from exc
        HTML = WeasyPrintHTML
    result: Any = HTML(string=build_html(md)).write_pdf()
    if not isinstance(result, bytes):
        raise TypeError("WeasyPrint did not return PDF bytes")
    return result
