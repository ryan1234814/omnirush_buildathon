"""Deterministic, file-backed pages used by the offline mock providers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


class _TextParser(HTMLParser):
    """Extract readable text from a saved HTML fixture without network access."""

    _ignored_tags = {"script", "style", "noscript"}

    def __init__(self) -> None:
        super().__init__()
        self._ignored_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._ignored_tags:
            self._ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self._ignored_tags and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth and data.strip():
            self.parts.append(" ".join(data.split()))


@dataclass(frozen=True, slots=True)
class MockPage:
    """One indexed local page in the mock corpus."""

    title: str
    url: str
    path: Path
    score: float
    published_date: str | None

    @property
    def text(self) -> str:
        """Return the saved page as normalized plain text."""

        parser = _TextParser()
        parser.feed(self.path.read_text(encoding="utf-8"))
        return " ".join(parser.parts).strip()


def corpus_index_path() -> Path:
    """Return the repository-relative corpus index path."""

    return Path(__file__).with_name("fixtures") / "corpus.json"


def load_corpus(index_path: str | Path | None = None) -> list[MockPage]:
    """Load and validate the local corpus index."""

    path = Path(index_path) if index_path else corpus_index_path()
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Mock corpus index is unreadable: {path}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("pages"), list):
        raise ValueError("Mock corpus index must contain a pages array")

    pages: list[MockPage] = []
    for item in payload["pages"]:
        if not isinstance(item, dict):
            continue
        title = item.get("title")
        url = item.get("url")
        relative_path = item.get("path")
        if not all(
            isinstance(value, str) and value.strip()
            for value in (title, url, relative_path)
        ):
            continue
        page_path = path.parent / relative_path
        if not page_path.is_file():
            raise ValueError(f"Mock corpus page is missing: {page_path}")
        pages.append(
            MockPage(
                title=title.strip(),
                url=url.strip(),
                path=page_path,
                score=float(item.get("score", 0.0)),
                published_date=item.get("published_date") or None,
            )
        )
    if not pages:
        raise ValueError("Mock corpus index contains no valid pages")
    return pages


def page_for_url(url: str, pages: list[MockPage] | None = None) -> MockPage | None:
    """Return a local page for a fixture URL, if one exists."""

    return next((page for page in (pages or load_corpus()) if page.url == url), None)
