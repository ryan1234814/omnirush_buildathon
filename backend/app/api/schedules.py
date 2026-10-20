"""Recurring report schedule endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.models import Schedule, ScheduleCreate
from app.scheduler import SchedulerService

router = APIRouter(prefix="/api/schedules", tags=["schedules"])


def _service(request: Request) -> SchedulerService:
    """Return the app-scoped scheduler service."""

    return request.app.state.scheduler


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_schedule(payload: ScheduleCreate, request: Request) -> Schedule:
    """Create one recurring schedule and return it with its first due time."""

    return _service(request).create(payload)


@router.get("", response_model=list[Schedule])
async def list_schedules(request: Request) -> list[Schedule]:
    """Return every persisted schedule."""

    return _service(request).list()


@router.delete("/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_schedule(schedule_id: str, request: Request) -> Response:
    """Remove one schedule by identifier."""

    if not _service(request).delete(schedule_id):
        raise HTTPException(status_code=404, detail="Schedule not found")
