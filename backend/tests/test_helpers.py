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


# ── retrieval (RAG) ───────────────────────────────────────────────────────────

from types import SimpleNamespace

from services.search_service import rank, tokenize


def _a(i, title, category="world", summary=""):
    return SimpleNamespace(id=i, title=title, category=category, summary=summary, raw_content="",
                           tags=[], deep_explanation=None, importance_score=0.5)


CORPUS = [
    _a(1, "Internationals hold three-point Presidents Cup lead over US", "sports"),
    _a(2, "The surprising reasons China is skeptical of A.I. safety calls", "world"),
    _a(3, "Decap is the man behind the drums behind your favorite song", "entertainment"),
    _a(4, "'Zombified' C.D.C., hobbled by cuts, struggles to fulfill scientific mission", "health"),
    _a(5, "Black hole jets reach far beyond galaxies", "science"),
]


def test_tokenize_normalises_acronyms_and_plurals():
    assert tokenize("The C.D.C.'s songs") == ["cdc", "song"]


@pytest.mark.parametrize("question, expected", [
    ("How is the International team doing against the United States in the Presidents Cup?", 1),
    ("Who is Decap and what does he do on popular songs?", 3),
    ("How have budget cuts affected the CDC?", 4),
])
def test_rank_finds_the_right_story(question, expected):
    assert rank(question, CORPUS)[0][1].id == expected


def test_rank_returns_nothing_for_uncovered_topics():
    assert rank("What happened with the Mars colony vote?", CORPUS) == []


def test_section_browse():
    assert [a.id for _, a in rank("science news", CORPUS)] == [5]


def test_scores_reject_nan():
    assert _parse_scores("[NaN, 0.4]", 2) == [0.5, 0.4]


def test_extract_json_can_require_objects():
    raw = 'Topics from headlines [3] and [7]: [{"topic": "x"}]'
    assert extract_json(raw, list, items=dict) == [{"topic": "x"}]


def test_india_never_pulls_stories_from_topic_sections():
    cricket = {"title": "India beat Pakistan as Kohli hits century in Delhi", "content": ""}
    assert not belongs_elsewhere(cricket, "sports")


def test_publisher_named_from_feed_url():
    from services.news_service import _source_name
    assert _source_name("Technology News Today, Latest Tech News", "https://www.thehindu.com/x.rss") == "The Hindu"


def test_rate_limit_wait_is_read_from_the_error():
    from services.llm_service import _retry_after
    err = Exception("Rate limit reached ... Please try again in 2.8275s. Need more tokens?")
    assert abs(_retry_after(err) - 3.3275) < 1e-6
    assert _retry_after(Exception("try again in 1m5.5s")) == 66.0
    assert _retry_after(Exception("no hint")) == 5.5


def test_long_rate_limit_pauses_all_calls(monkeypatch):
    import asyncio
    from services import llm_service

    class RateLimit(Exception):
        status_code = 429

    calls = []

    async def fake_call(*a, **kw):
        calls.append(1)
        raise RateLimit("Rate limit reached for requests per day. Please try again in 12m30s.")

    monkeypatch.setattr(llm_service.settings, "GROQ_API_KEY", "test-key")
    monkeypatch.setattr(llm_service, "_call", fake_call)
    monkeypatch.setattr(llm_service, "_paused_until", {})

    for _ in range(2):
        try:
            asyncio.run(llm_service.chat("hi"))
            raise AssertionError("expected LLMRateLimited")
        except llm_service.LLMRateLimited as e:
            assert e.seconds > 700
    assert len(calls) == 1                     # the second call didn't hit the provider at all
    assert llm_service.pause_remaining() > 700


def test_invented_name_candidates_are_flagged():
    from agents.summarizer_agent import invented_names
    source = "Scheffler and Thomas shine for USA in incredible Presidents Cup victory! Team USA dominated."
    text = "Collin Scheffler and Tommy Thomas won for Team USA at the Presidents Cup."
    assert invented_names(text, source) == ["Collin Scheffler", "Tommy Thomas"]
    assert invented_names("Scottie Scheffler won.", "Scottie Scheffler won the Masters") == []   # stated in full


def test_name_check_asks_the_model_and_accepts_only_small_edits(monkeypatch):
    import asyncio
    from agents import summarizer_agent as sa

    analysis = {"summary": "Collin Scheffler starred as the US won the Ryder Cup rematch.",
                "deep_explanation": "Rising star Collin Scheffler led the way.", "why_it_matters": "Big win.",
                "background_info": "", "tags": []}
    calls = []

    async def fake_chat(prompt, **kw):
        calls.append(prompt)
        return ('{"summary": "Scheffler starred as the US won the Ryder Cup rematch.",'
                ' "deep_explanation": "Rising star Scheffler led the way.", "why_it_matters": "Big win."}')

    monkeypatch.setattr(sa.llm_service, "chat", fake_chat)
    fixed = asyncio.run(sa.SummarizerAgent()._verify_names(analysis, "Scheffler shines for USA", "Scheffler won."))
    assert fixed["summary"] == "Scheffler starred as the US won the Ryder Cup rematch."
    assert "Collin Scheffler" in calls[0]

    calls.clear()
    clean = {**analysis, "summary": "Scheffler starred.", "deep_explanation": "Scheffler led."}
    assert asyncio.run(sa.SummarizerAgent()._verify_names(clean, "Scheffler shines", "Scheffler won.")) == clean
    assert calls == []   # nothing flagged → no extra LLM call



def test_backup_provider_takes_over_when_main_is_rate_limited(monkeypatch):
    import asyncio
    from services import llm_service

    class RateLimit(Exception):
        status_code = 429

    calls = []

    async def fake_call(provider, *a, **kw):
        calls.append(provider)
        if provider == "groq":
            raise RateLimit("Rate limit reached on tokens per minute. Please try again in 20s.")
        return "answer from gemini"

    monkeypatch.setattr(llm_service.settings, "GROQ_API_KEY", "g")
    monkeypatch.setattr(llm_service.settings, "GEMINI_API_KEY", "m")
    monkeypatch.setattr(llm_service, "_call", fake_call)
    monkeypatch.setattr(llm_service, "_paused_until", {})

    assert llm_service.settings.llm_providers == ["groq", "gemini"]
    assert asyncio.run(llm_service.chat("hi")) == "answer from gemini"
    assert calls == ["groq", "gemini"]           # no 20 s wait — handed over at once
    # While Groq is paused, calls go straight to Gemini
    assert asyncio.run(llm_service.chat("again")) == "answer from gemini"
    assert calls == ["groq", "gemini", "gemini"]


def test_fallback_can_be_disabled(monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "GROQ_API_KEY", "g")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "m")
    monkeypatch.setattr(settings, "LLM_FALLBACK_PROVIDER", "none")
    assert settings.llm_providers == ["groq"]
