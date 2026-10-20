"""Text renderers for the supported report distribution formats."""

from __future__ import annotations

import re


def _body(report_md: str) -> str:
    """Remove the generated title and references for prose-focused formats."""

    body = re.sub(r"\A# Research report:.*?\n+", "", report_md, count=1, flags=re.IGNORECASE)
    return re.split(r"(?im)^##\s+Sources\s*$", body, maxsplit=1)[0].strip()


def render_executive_summary(report_md: str) -> str:
    """Render a compact executive summary while retaining Markdown."""

    body = _body(report_md)
    paragraphs = [part.strip() for part in body.split("\n\n") if part.strip()]
    return "# Executive summary\n\n" + "\n\n".join(paragraphs[:3]) + "\n"


def render_blog(report_md: str) -> str:
    """Render an accessible blog post from report sections."""

    return f"# Research briefing\n\n{_body(report_md)}\n"


def render_linkedin(report_md: str) -> str:
    """Render a short LinkedIn-ready digest."""

    body = _body(report_md)
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    bullets = "\n".join(f"- {line.lstrip('#- ').strip()}" for line in lines[:6])
    return f"# LinkedIn digest\n\n{bullets}\n\n#Research #Insights\n"


def render_marp(report_md: str) -> str:
    """Render a Marp-compatible slide deck with one section per report heading."""

    body = _body(report_md)
    sections = re.split(r"(?m)^(?=##\s+)", body)
    slides = [part.strip() for part in sections if part.strip()]
    header = "---\nmarp: true\ntheme: default\npaginate: true\n---\n\n"
    return header + "\n\n---\n\n".join(slides) + "\n"


RENDERERS = {
    "executive": render_executive_summary,
    "blog": render_blog,
    "linkedin": render_linkedin,
    "slides": render_marp,
    "marp": render_marp,
}
