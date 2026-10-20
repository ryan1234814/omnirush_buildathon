"""Pinned synthesis prompt and bounded source-context formatting."""

from collections.abc import Sequence

from app.models import SourceEntry

SYNTHESIS_SYSTEM_PROMPT = """You are a citation-strict research report writer.

Write a concise Markdown report with a title and multiple `##` sections.
Every factual sentence MUST end with a citation like [1], using only the
source IDs supplied in the user message. A citation may only support a claim
that appears in that source's excerpt. Do not invent facts or citations.
Use ordinary ASCII square brackets exactly as shown; never use full-width
citation brackets such as 【1】.

Do not write URLs anywhere in the report body. Do not add a `## Sources`
section; the application generates that section from the source registry.
Do not use outside knowledge. If context is insufficient, say so and mark the
statement exactly as `*(unverified)*`.

Return only the Markdown report, with no preamble or commentary.
"""


def build_synthesis_user_prompt(
    topic: str, excerpts: str, follow_up_prompt: str | None = None
) -> str:
    """Build the user prompt containing only the bounded registry context."""

    refinement = f"\nRefinement request: {follow_up_prompt}\n" if follow_up_prompt else ""
    return f"""Research topic: {topic}
{refinement}

Use only these source excerpts:

{excerpts}

Now write the citation-strict Markdown report."""


def format_excerpts(entries: Sequence[SourceEntry]) -> str:
    """Format registry entries as labeled fenced blocks for the model."""

    blocks: list[str] = []
    for entry in entries:
        blocks.append(f"```text\n[{entry.id}] {entry.title} — {entry.url}\n{entry.excerpt}\n```")
    return "\n\n".join(blocks) or "```text\nNo source excerpts are available.\n```"
