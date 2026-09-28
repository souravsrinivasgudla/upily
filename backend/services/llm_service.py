"""
LLMService — single place for all LLM calls (Groq, OpenAI or Anthropic).

`chat()` raises instead of returning placeholder text, so callers can tell
"no key configured" apart from "provider failed" and show the right message.
"""
import asyncio
import logging
import re
import time

from config import settings

log = logging.getLogger(__name__)


class LLMError(Exception):
    """The provider call failed (timeout, rate limit, bad model, …)."""


class LLMNotConfigured(LLMError):
    """No API key is set for the selected LLM_PROVIDER."""


class LLMRateLimited(LLMError):
    """The provider asked us to back off for longer than is worth waiting inline."""

    def __init__(self, seconds: float):
        super().__init__(f"LLM rate limit — paused for {seconds:.0f}s")
        self.seconds = seconds


# When the provider asks for a long back-off (e.g. a daily request cap), every caller
# stops calling until this monotonic time instead of each retrying on its own.
_paused_until = 0.0


def pause_remaining() -> float:
    return max(0.0, _paused_until - time.monotonic())


def is_llm_configured() -> bool:
    return settings.llm_configured


def is_reasoning_model(model: str) -> bool:
    return settings.LLM_PROVIDER == "groq" and model.startswith(("openai/gpt-oss", "qwen/qwen3"))


_client = None  # created lazily and reused so connections are pooled


def _get_client():
    global _client
    if _client is None:
        key, timeout = settings.llm_api_key, settings.LLM_TIMEOUT_SECONDS
        if settings.LLM_PROVIDER == "groq":
            from groq import AsyncGroq
            _client = AsyncGroq(api_key=key, timeout=timeout, max_retries=0)
        elif settings.LLM_PROVIDER == "openai":
            from openai import AsyncOpenAI
            _client = AsyncOpenAI(api_key=key, timeout=timeout, max_retries=0)
        else:
            import anthropic
            _client = anthropic.AsyncAnthropic(api_key=key, timeout=timeout, max_retries=0)
    return _client


async def _call(prompt: str, system: str, max_tokens: int, temperature: float) -> str:
    client = _get_client()
    if settings.LLM_PROVIDER == "anthropic":
        resp = await client.messages.create(
            model=settings.llm_model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()

    extra = {}
    if is_reasoning_model(settings.llm_model):
        # Hidden reasoning tokens count toward max_tokens — leave headroom so the answer isn't cut off
        extra["extra_body"] = {"reasoning_effort": settings.LLM_REASONING_EFFORT}
        max_tokens += 1024
    resp = await client.chat.completions.create(
        model=settings.llm_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": prompt},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
        **extra,
    )
    return (resp.choices[0].message.content or "").strip()


async def chat(
    prompt: str,
    system: str = "You are a helpful AI assistant.",
    max_tokens: int = 1500,
    temperature: float = 0.3,
    retries: int = 1,
) -> str:
    """Send a prompt to the configured LLM and return the response text."""
    global _paused_until
    if not settings.llm_configured:
        raise LLMNotConfigured(
            f"No API key set for LLM_PROVIDER={settings.LLM_PROVIDER}"
        )
    if pause_remaining():
        raise LLMRateLimited(pause_remaining())

    last_error: Exception | None = None
    attempt, rate_limit_waits = 0, 0
    while True:
        try:
            text = await _call(prompt, system, max_tokens, temperature)
            if not text:
                raise LLMError("Empty response from LLM")
            return text
        except LLMError as e:
            last_error = e
        except Exception as e:  # provider SDK errors
            last_error = e

        status = getattr(last_error, "status_code", None)
        if status == 429:
            wait = _retry_after(last_error)
            if wait > MAX_RATE_LIMIT_SLEEP:
                # A long back-off (daily cap, big token debt): stop everyone, don't spin
                _paused_until = time.monotonic() + wait
                log.warning("LLM rate limit: pausing AI calls for %.0fs (provider said: %s)",
                            wait, str(last_error)[:240])
                raise LLMRateLimited(wait) from last_error
            if rate_limit_waits < MAX_RATE_LIMIT_WAITS:
                # Per-minute limit: wait as long as the provider asks, then retry
                rate_limit_waits += 1
                log.info("LLM rate-limited; waiting %.1fs (%d/%d)", wait, rate_limit_waits, MAX_RATE_LIMIT_WAITS)
                await asyncio.sleep(wait)
                continue

        log.warning("LLM call failed (attempt %d/%d, %s/%s): %s: %s",
                    attempt + 1, retries + 1, settings.LLM_PROVIDER, settings.llm_model,
                    type(last_error).__name__, str(last_error)[:300])
        if status in (400, 401, 403, 404) or attempt >= retries:
            break   # bad key / unknown model — retrying won't help; or out of retries
        attempt += 1
        await asyncio.sleep(1.5 * attempt)

    raise LLMError(f"LLM call failed: {type(last_error).__name__}") from last_error


MAX_RATE_LIMIT_WAITS = 4
MAX_RATE_LIMIT_SLEEP = 60.0     # longer requested waits pause all calls instead (see LLMRateLimited)
_TRY_AGAIN = re.compile(r"try again in (?:(\d+)m)?([\d.]+)s", re.I)


def _retry_after(error: Exception) -> float:
    """Seconds to wait before retrying a 429, from the Retry-After header or the error text."""
    wait = None
    headers = getattr(getattr(error, "response", None), "headers", None) or {}
    try:
        wait = float(headers.get("retry-after"))
    except (TypeError, ValueError):
        m = _TRY_AGAIN.search(str(error))
        if m:
            wait = int(m.group(1) or 0) * 60 + float(m.group(2))
    return (wait or 5.0) + 0.5
