"""Text helpers: HTML stripping, truncation, tolerant JSON extraction from LLM output."""
import html
import json
import re
import warnings
from typing import Any, Optional

from bs4 import BeautifulSoup, MarkupResemblesLocatorWarning


def strip_html(text: Optional[str]) -> str:
    if not text:
        return ""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", MarkupResemblesLocatorWarning)
        clean = BeautifulSoup(text, "html.parser").get_text(" ")
    return " ".join(html.unescape(clean).split())


def truncate(text: str, max_len: int) -> str:
    """Cut at a word boundary and add an ellipsis."""
    if len(text) <= max_len:
        return text
    cut = text[:max_len].rsplit(" ", 1)[0].rstrip(",;:-")
    return cut + "…"


def clean_excerpt(text: Optional[str], max_len: int) -> str:
    return truncate(strip_html(text), max_len)


def extract_json(raw: Optional[str], expect: type = dict) -> Any:
    """
    Return the first JSON value of type `expect` found in `raw`, or None.
    Tolerates markdown fences and chatter before/after the JSON.
    """
    if not raw:
        return None
    opener = "{" if expect is dict else "["
    decoder = json.JSONDecoder()
    text = re.sub(r"```(?:json)?", "", raw)
    idx = text.find(opener)
    while idx != -1:
        try:
            value, _ = decoder.raw_decode(text, idx)
            if isinstance(value, expect):
                return value
        except json.JSONDecodeError:
            pass
        idx = text.find(opener, idx + 1)
    return None


def as_text(value: Any, max_len: int = 6000) -> str:
    """Coerce LLM field values (str / list / dict / None) to clean display text."""
    if value is None:
        return ""
    if isinstance(value, list):
        value = "\n\n".join(as_text(v, max_len) for v in value if v)
    elif isinstance(value, dict):
        value = "\n\n".join(as_text(v, max_len) for v in value.values() if v)
    return truncate(str(value).strip(), max_len)
