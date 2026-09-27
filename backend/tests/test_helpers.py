from datetime import datetime, timedelta, timezone

import pytest

from agents.news_agent import _parse_scores
from agents.qa_agent import clean_answer
from agents.summarizer_agent import normalize_analysis
from services.dates import parse_date
from services.llm_service import LLMError
from services.news_service import belongs_elsewhere, keyword_hits
from services.text import extract_json, strip_html

NOW = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)


# ── dates ─────────────────────────────────────────────────────────────────────

def test_us_zone_abbreviations_are_respected():
    dt = parse_date("Sun, 27 Sep 2026 06:00:00 EST", now=NOW)
    assert dt == datetime(2026, 9, 27, 11, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("raw, delta", [
    ("3 hours ago", timedelta(hours=3)),
    ("2 days ago", timedelta(days=2)),
    ("1 week ago", timedelta(weeks=1)),
    ("an hour ago", timedelta(hours=1)),
])
def test_relative_dates(raw, delta):
    assert parse_date(raw, now=NOW) == NOW - delta


def test_serpapi_format():
    assert parse_date("09/26/2026, 07:00 AM, +0000 UTC", now=NOW) == datetime(2026, 9, 26, 7, tzinfo=timezone.utc)


def test_unknown_dates_are_none_not_now():
    assert parse_date(None) is None
    assert parse_date("not a date") is None


def test_future_dates_are_clamped():
    assert parse_date("2030-01-01T00:00:00Z", now=NOW) == NOW


# ── text / JSON ───────────────────────────────────────────────────────────────

def test_strip_html():
    assert strip_html("<p>Hello&nbsp;<b>world</b> &amp; co</p>") == "Hello world & co"


def test_extract_json_tolerates_fences_and_chatter():
    raw = 'Sure! Here you go:\n```json\n{"summary": "x", "tags": ["a"]}\n```\nHope that helps {}'
    assert extract_json(raw, dict) == {"summary": "x", "tags": ["a"]}
    assert extract_json("[MOCK] then [0.2, 0.9]", list) == [0.2, 0.9]
    assert extract_json("no json here", dict) is None


def test_scores_are_clamped_and_padded():
    assert _parse_scores("[1.7, -2, \"0.4\", \"x\"]", 5) == [1.0, 0.0, 0.4, 0.5, 0.5]


def test_normalize_analysis_coerces_types():
    out = normalize_analysis({
        "summary": "S", "deep_explanation": ["p1", "p2"],
        "why_it_matters": None, "tags": "#Gaza, news, Federal Reserve, gaza",
    })
    assert out["deep_explanation"] == "p1\n\np2"
    assert out["why_it_matters"] == ""
    assert out["tags"] == ["gaza", "federal-reserve"]


def test_normalize_analysis_rejects_empty():
    with pytest.raises(LLMError):
        normalize_analysis({"summary": "", "deep_explanation": ""})


def test_clean_answer_strips_markdown_for_plain_text_chat():
    assert clean_answer("## Top\n- **Big** win 【sports · BBC】 done") == "Top\n- Big win (sports · BBC) done"


# ── categories ────────────────────────────────────────────────────────────────

def test_keywords_match_whole_words_only():
    assert keyword_hits("Mayor said the rain will start again", "technology") == 0
    assert keyword_hits("New AI chip from Nvidia", "technology") >= 2


def test_belongs_elsewhere():
    sports = {"title": "Coach praises team after championship match", "content": ""}
    assert belongs_elsewhere(sports, "technology")
    assert not belongs_elsewhere(sports, "sports")
    vague = {"title": "A quiet afternoon", "content": ""}
    assert not belongs_elsewhere(vague, "science")
