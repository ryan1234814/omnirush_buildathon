"""Deterministic report assembly and references generation."""

from __future__ import annotations

import re

from app.models import SourceRegistry


def _without_model_sources(md: str) -> str:
    """Remove a model-generated Sources section before adding the canonical one."""

    match = re.search(r"(?im)^##\s+Sources\s*$", md)
    return md[: match.start()].rstrip() if match else md.strip()


def assemble(topic: str, body: str, registry: SourceRegistry) -> str:
    """Assemble a report whose references are generated only from registry data."""

    title = f"# Research report: {topic.strip()}"
    clean_body = _without_model_sources(body)
    sections = [title, clean_body] if clean_body else [title]
    sections.append("## Sources")
    if registry.entries:
        sections.extend(
            f"**[{entry.id}] {entry.title}** — [{entry.url}]({entry.url})"
            for entry in registry.entries
        )
    else:
        sections.append("_No sources were available._")
    return "\n\n".join(sections).strip() + "\n"
