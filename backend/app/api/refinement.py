"""Follow-up chat against completed reports (iterative refinement)."""

from __future__ import annotations

import logging
import re
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, status
from openai import AsyncOpenAI

from app.models import FollowUpRequest, ReportRun, SourceRegistry
from app.prompts.synthesis import SYNTHESIS_SYSTEM_PROMPT, format_excerpts

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/reports", tags=["refinement"])
_CITATION = re.compile(r"\[(\d+)\]")
MAX_HISTORY_MESSAGES = 20


def _conversations(request: Request) -> dict[str, list[dict[str, str]]]:
    """Return the app-scoped follow-up conversation store."""

    conversations: dict[str, list[dict[str, str]]] = request.app.state.follow_up_conversations
    return conversations


def _extract_citations(answer: str, run: ReportRun) -> list[int]:
    """Keep only citation numbers that exist in the run's source registry."""

    valid = {entry.id for entry in run.sources}
    return sorted({int(match) for match in _CITATION.findall(answer) if int(match) in valid})


def _mock_answer(message: str, run: ReportRun) -> str:
    """Return a deterministic offline answer that reuses the citation registry."""

    if not run.sources:
        return (
            f"The report on {run.topic} has no cached sources, so this follow-up "
            "cannot be grounded in cited evidence."
        )
    return (
        f"Based on the cached research for {run.topic}, the collected evidence addresses "
        f"“{message}”: the report's primary source supports its main conclusion [1]. "
        "Ask a narrower question to focus on one finding."
    )


async def _answer_with_llm(
    request: Request,
    message: str,
    run: ReportRun,
    history: list[dict[str, str]],
) -> str:
    """Answer one follow-up through the configured OpenAI-compatible provider."""

    settings = request.app.state.settings
    if not settings.llm_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Follow-up LLM is not configured",
        )
    client = AsyncOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        timeout=30.0,
        max_retries=0,
    )
    registry = SourceRegistry(entries=run.sources)
    context = (
        f"Report topic: {run.topic}\n\nReport Markdown:\n{run.report_md}\n\n"
        f"Numbered source excerpts:\n{format_excerpts(registry.entries)}"
    )
    messages = [
        {
            "role": "system",
            "content": (
                SYNTHESIS_SYSTEM_PROMPT
                + " Answer the follow-up using ONLY the report and numbered excerpts above. "
                "Reuse existing [n] citation numbers and never invent new ones."
            ),
        }
    ]
    messages.extend(history)
    messages.append({"role": "user", "content": f"{context}\n\nFollow-up question: {message}"})
    response = await client.chat.completions.create(
        model=settings.llm_model,
        messages=messages,
        timeout=30.0,
    )
    choices = getattr(response, "choices", None) or []
    content = getattr(getattr(choices[0], "message", None) if choices else None, "content", None)
    if not isinstance(content, str) or not content.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Follow-up response was empty",
        )
    return content.strip()


@router.post("/{run_id}/chat")
async def follow_up_chat(
    run_id: str,
    payload: FollowUpRequest,
    request: Request,
) -> dict[str, object]:
    """Answer one refinement question from the completed run's cached evidence."""

    bus = request.app.state.event_bus
    try:
        run = await bus.get_snapshot(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Report run not found") from exc
    if run.status != "completed" or not run.report_md:
        raise HTTPException(
            status_code=409,
            detail="Follow-up chat requires a completed report",
        )

    settings = request.app.state.settings
    conversations = _conversations(request)
    conversation_id = payload.conversation_id or uuid.uuid4().hex
    history = conversations.get(conversation_id, [])

    if settings.mock_mode or settings.search_provider == "mock":
        answer = _mock_answer(payload.message, run)
    else:
        answer = await _answer_with_llm(request, payload.message, run, history)

    history = [
        *history,
        {"role": "user", "content": payload.message},
        {"role": "assistant", "content": answer},
    ][-MAX_HISTORY_MESSAGES:]
    conversations[conversation_id] = history
    return {
        "conversation_id": conversation_id,
        "answer": answer,
        "citations": _extract_citations(answer, run),
        "created_at": datetime.now(UTC).isoformat(),
    }
