"""Non-blocking completion notification abstractions."""

from __future__ import annotations

import asyncio
import logging
import smtplib
import uuid
from datetime import UTC, datetime
from email.message import EmailMessage
from typing import Protocol

import httpx

from app.config import Settings
from app.models import Notification, ReportRun
from app.storage import load_notifications, save_notifications

logger = logging.getLogger(__name__)


class NotificationSink(Protocol):
    async def send(self, snapshot: ReportRun) -> None:
        """Deliver one completion notification."""


class WebhookNotifier:
    """POST a JSON completion payload to a configured webhook."""

    def __init__(self, url: str, timeout_seconds: float = 5.0) -> None:
        self.url = url
        self.timeout_seconds = timeout_seconds

    async def send(self, snapshot: ReportRun) -> None:
        payload = {
            "event": "report_completed",
            "run_id": snapshot.id,
            "topic": snapshot.topic,
            "status": snapshot.status,
            "outcome": snapshot.outcome,
            "report_url": f"/api/reports/{snapshot.id}/report.md",
        }
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(self.url, json=payload)
            response.raise_for_status()


class EmailNotifier:
    """SMTP adapter executed in a worker thread so it cannot block the loop."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def send(self, snapshot: ReportRun) -> None:
        await asyncio.to_thread(self._send_sync, snapshot)

    def _send_sync(self, snapshot: ReportRun) -> None:
        if not self.settings.smtp_host or not self.settings.notification_email_to:
            return
        message = EmailMessage()
        message["From"] = self.settings.notification_email_from
        message["To"] = self.settings.notification_email_to
        message["Subject"] = f"Research report completed: {snapshot.topic}"
        message.set_content(
            f"Run {snapshot.id} finished with outcome {snapshot.outcome}.\n"
            f"Report: /api/reports/{snapshot.id}/report.md\n"
        )
        with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=5) as smtp:
            if self.settings.smtp_username:
                smtp.starttls()
                smtp.login(self.settings.smtp_username, self.settings.smtp_password or "")
            smtp.send_message(message)


async def send_completion_notifications(snapshot: ReportRun, settings: Settings) -> None:
    """Attempt configured sinks independently and log failures without raising."""

    sinks: list[NotificationSink] = []
    if settings.completion_webhook_url:
        sinks.append(WebhookNotifier(settings.completion_webhook_url))
    if settings.notification_email_to and settings.smtp_host:
        sinks.append(EmailNotifier(settings))
    results = await asyncio.gather(*(sink.send(snapshot) for sink in sinks), return_exceptions=True)
    for result in results:
        if isinstance(result, Exception):
            logger.warning("Completion notification failed (%s)", type(result).__name__)


def schedule_completion_notifications(
    snapshot: ReportRun, settings: Settings, tasks: set[object]
) -> None:
    """Schedule delivery and return immediately to the report pipeline."""

    if not settings.completion_webhook_url and not (
        settings.notification_email_to and settings.smtp_host
    ):
        return
    task = asyncio.create_task(send_completion_notifications(snapshot, settings))
    tasks.add(task)
    task.add_done_callback(tasks.discard)


def record_run_notification(snapshot: ReportRun, settings: Settings) -> None:
    """Store one in-app notification for a terminated run, newest first."""

    completed = snapshot.status == "completed"
    notification = Notification(
        id=uuid.uuid4().hex,
        type="run_completed" if completed else "run_failed",
        title=(
            f"Report ready: {snapshot.topic}" if completed else f"Report failed: {snapshot.topic}"
        ),
        message=(
            f"Run {snapshot.id} finished with outcome {snapshot.outcome}."
            if completed
            else f"Run {snapshot.id} failed: {snapshot.error}"
        ),
        run_id=snapshot.id,
        created_at=datetime.now(UTC),
    )
    notifications = load_notifications(settings.runs_dir)
    notifications = [item for item in notifications if item.run_id != snapshot.id]
    notifications.insert(0, notification)
    save_notifications(notifications[:100], settings.runs_dir)
