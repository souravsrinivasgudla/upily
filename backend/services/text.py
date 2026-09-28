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


def extract_json(raw: Optional[str], expect: type = dict, items: Optional[type] = None) -> Any:
    """
    Return the first JSON value of type `expect` found in `raw`, or None.
    With `items`, a list only counts if it is non-empty and every element is of that type
    (so "headlines [3] and [7]: [{...}]" yields the list of objects, not [3]).
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
            if isinstance(value, expect) and (
                items is None or (value and all(isinstance(v, items) for v in value))
            ):
                return value
        except json.JSONDecodeError:
            pass
        idx = text.find(opener, idx + 1)
    return None


# LLMs often emit typographic look-alikes (narrow no-break spaces, non-breaking hyphens).
# They render fine but break text matching (search, name checks), so store plain forms.
_LOOKALIKES = str.maketrans({
    " ": " ", " ": " ", " ": " ", " ": " ", " ": " ",
    "‑": "-", "‐": "-",
})


def normalize_chars(text: str) -> str:
    return text.translate(_LOOKALIKES)


def as_text(value: Any, max_len: int = 6000) -> str:
    """Coerce LLM field values (str / list / dict / None) to clean display text."""
    if value is None:
        return ""
    if isinstance(value, list):
        value = "\n\n".join(as_text(v, max_len) for v in value if v)
    elif isinstance(value, dict):
        value = "\n\n".join(as_text(v, max_len) for v in value.values() if v)
    return truncate(normalize_chars(str(value)).strip(), max_len)
