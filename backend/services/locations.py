"""
Location hierarchy for local news: India → state / union territory → district.

Data: data/india_districts.json (36 states and UTs, 780 districts, checked against
official district counts). The API keeps a `country` level so other countries can be
added later without changing the frontend contract.
"""
import json
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

DATA = Path(__file__).resolve().parents[1] / "data" / "india_districts.json"
COUNTRIES = [{"code": "IN", "name": "India"}]


@lru_cache(maxsize=1)
def _india() -> Dict:
    return json.loads(DATA.read_text(encoding="utf-8"))


def countries() -> List[Dict[str, str]]:
    return COUNTRIES


def country_name(code: str) -> Optional[str]:
    return next((c["name"] for c in COUNTRIES if c["code"] == (code or "").upper()), None)


def states(code: str = "IN") -> List[str]:
    return sorted(_india()["states"]) if (code or "").upper() == "IN" else []


def districts(code: str, state: str) -> List[str]:
    if (code or "").upper() != "IN":
        return []
    return sorted(_india()["states"].get(state, []))


def search_name(district: str) -> str:
    """How a district is usually written in the news (e.g. 'Ananthapuramu' → 'Anantapur')."""
    return _india()["search_names"].get(district, district)


def validate(code: str, state: Optional[str], district: Optional[str]) -> Optional[str]:
    """Error message for an unknown location, or None when it's valid."""
    code = (code or "").upper()
    if not country_name(code):
        return "Local news currently covers India only"
    if not state:
        return "Choose a state or union territory"
    if state not in states(code):
        return f"Unknown state or union territory '{state}'"
    if district and district not in districts(code, state):
        return f"'{district}' is not a district of {state}"
    return None
