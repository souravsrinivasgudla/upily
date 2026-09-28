from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import RateLimiter
from services import local_news, locations

router = APIRouter()
local_limit = RateLimiter(max_calls=20, per_seconds=60, scope="local")


@router.get("/locations/countries")
async def list_countries():
    return {"countries": locations.countries()}


@router.get("/locations/states")
async def list_states(country: str = Query("IN", min_length=2, max_length=2)):
    if not locations.country_name(country):
        raise HTTPException(status_code=404, detail="Local news currently covers India only")
    return {"country": country.upper(), "states": locations.states(country)}


@router.get("/locations/districts")
async def list_districts(state: str = Query(..., max_length=100),
                         country: str = Query("IN", min_length=2, max_length=2)):
    if state not in locations.states(country):
        raise HTTPException(status_code=404, detail=f"Unknown state or union territory '{state}'")
    return {"country": country.upper(), "state": state, "districts": locations.districts(country, state)}


@router.get("/local", dependencies=[Depends(local_limit)])
async def local_news_for(
    state: str = Query(..., max_length=100),
    district: Optional[str] = Query(None, max_length=100),
    country: str = Query("IN", min_length=2, max_length=2),
):
    """Local stories for a state/UT and optional district. Cached per location for 20 minutes."""
    country = country.upper()
    district = district or None
    error = locations.validate(country, state, district)
    if error:
        raise HTTPException(status_code=404, detail=error)
    return await local_news.get_local(state, district, country)
