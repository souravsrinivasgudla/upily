from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import trending_limit
from services import calendar_service

router = APIRouter()


@router.get("/calendar", dependencies=[Depends(trending_limit)])
async def economic_calendar(
    impact: Optional[str] = Query(None, description="Comma-separated: High,Medium,Low,Holiday"),
):
    """This week's economic calendar (Forex Factory), optionally filtered by impact."""
    try:
        week = await calendar_service.get_week()
    except Exception:
        raise HTTPException(status_code=503, detail="The economic calendar is unavailable right now.")
    wanted = {i.strip().title() for i in impact.split(",")} if impact else None
    return {**week, "events": calendar_service.filter_events(week["events"], wanted)}
