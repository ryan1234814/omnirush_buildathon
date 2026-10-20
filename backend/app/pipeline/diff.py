"""Deterministic comparison of two reports on the same topic."""

from __future__ import annotations

import difflib
import re

from app.models import ReportRun


def _sections(report_md: str | None) -> dict[str, str]:
    """Split a report into heading-keyed section bodies for change tracking."""

    sections: dict[str, list[str]] = {}
    current = "Summary"
    for line in (report_md or "").splitlines():
        heading = re.match(r"^(#{1,3})\s+(.*?)\s*$", line)
        if heading:
            current = heading.group(2)
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line)
    return {name: "\n".join(lines).strip() for name, lines in sections.items()}


def section_changes(previous: ReportRun, current: ReportRun) -> list[dict[str, object]]:
    """Compare report sections and emit the browser-facing change records."""

    previous_sections = _sections(previous.report_md)
    current_sections = _sections(current.report_md)
    changes: list[dict[str, object]] = []
    for name, body in current_sections.items():
        if name not in previous_sections:
            changes.append(
                {"section": name, "before": None, "after": body, "status": "added"}
            )
        elif previous_sections[name] != body:
            changes.append(
                {
                    "section": name,
                    "before": previous_sections[name],
                    "after": body,
                    "status": "changed",
                }
            )
    for name, body in previous_sections.items():
        if name not in current_sections:
            changes.append(
                {"section": name, "before": body, "after": None, "status": "removed"}
            )
    return changes


def diff_reports(previous: ReportRun, current: ReportRun) -> dict[str, object]:
    """Describe source churn, ranking changes, and report text changes."""

    previous_by_url = {source.url: source for source in previous.sources}
    current_by_url = {source.url: source for source in current.sources}
    added = [
        source.model_dump(mode="json")
        for url, source in current_by_url.items()
        if url not in previous_by_url
    ]
    removed = [
        source.model_dump(mode="json")
        for url, source in previous_by_url.items()
        if url not in current_by_url
    ]
    previous_rank = {source.url: index for index, source in enumerate(previous.sources, start=1)}
    current_rank = {source.url: index for index, source in enumerate(current.sources, start=1)}
    ranking_changes = [
        {"url": url, "from": previous_rank[url], "to": current_rank[url]}
        for url in previous_rank.keys() & current_rank.keys()
        if previous_rank[url] != current_rank[url]
    ]
    before = (previous.report_md or "").splitlines()
    after = (current.report_md or "").splitlines()
    text_diff = list(
        difflib.unified_diff(
            before, after, fromfile=previous.id, tofile=current.id, lineterm=""
        )
    )
    changes = section_changes(previous, current)
    summary = (
        f"{len(added)} source(s) added, {len(removed)} source(s) removed, "
        f"{len(changes)} section change(s) detected"
    )
    return {
        "topic": current.topic,
        "previous_run_id": previous.id,
        "current_run_id": current.id,
        # The browser views the newer run and compares it against an older one.
        "base_run_id": current.id,
        "compare_run_id": previous.id,
        "summary": summary,
        "changes": changes,
        "source_additions": added,
        "source_removals": removed,
        "ranking_changes": ranking_changes,
        "text_changed": before != after,
        "text_diff": text_diff,
    }
