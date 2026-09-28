"""
LLMService — single place for all LLM calls (Groq, OpenAI, Anthropic or Gemini).

Providers are tried in order (settings.llm_providers): the main LLM_PROVIDER, then the
backup (Gemini when GEMINI_API_KEY is set). While the main provider is rate-limited or
failing, requests go straight to the backup instead of waiting.

`chat()` raises instead of returning placeholder text, so callers can tell
"no key configured" apart from "provider failed" and show the right message.
"""
import asyncio
import logging
import re
import time
from typing import Dict, Optional

from config import settings

log = logging.getLogger(__name__)

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


class LLMError(Exception):
    """The provider call failed (timeout, rate limit, bad model, …)."""


class LLMNotConfigured(LLMError):
    """No API key is set for any configured provider."""


class LLMRateLimited(LLMError):
    """Every provider asked us to back off for longer than is worth waiting inline."""

    def __init__(self, seconds: float):
        super().__init__(f"LLM rate limit — paused for {seconds:.0f}s")
        self.seconds = seconds


# Per provider: monotonic time until which we don't call it (after a long back-off)
_paused_until: Dict[str, float] = {}


def _pause_left(provider: str) -> float:
    return max(0.0, _paused_until.get(provider, 0.0) - time.monotonic())


def pause_remaining() -> float:
    """Seconds until *some* provider is usable again (0 = one is usable now)."""
    providers = settings.llm_providers
    return min((_pause_left(p) for p in providers), default=0.0) if providers else 0.0


def is_llm_configured() -> bool:
    return settings.llm_configured


def is_reasoning_model(model: str, provider: Optional[str] = None) -> bool:
    return (provider or settings.LLM_PROVIDER) == "groq" and model.startswith(("openai/gpt-oss", "qwen/qwen3"))


_clients: Dict[str, object] = {}   # created lazily per provider and reused (connection pooling)


def _client(provider: str):
    if provider not in _clients:
        key, timeout = settings.api_key_for(provider), settings.LLM_TIMEOUT_SECONDS
        if provider == "groq":
            from groq import AsyncGroq
            _clients[provider] = AsyncGroq(api_key=key, timeout=timeout, max_retries=0)
        elif provider in ("openai", "gemini"):
            from openai import AsyncOpenAI
            # Gemini offers an OpenAI-compatible endpoint
            base_url = GEMINI_BASE_URL if provider == "gemini" else None
            _clients[provider] = AsyncOpenAI(api_key=key, base_url=base_url, timeout=timeout, max_retries=0)
        else:
            import anthropic
            _clients[provider] = anthropic.AsyncAnthropic(api_key=key, timeout=timeout, max_retries=0)
    return _clients[provider]


async def _call(provider: str, prompt: str, system: str, max_tokens: int, temperature: float) -> str:
    client = _client(provider)
    model = settings.model_for(provider)
    if provider == "anthropic":
        resp = await client.messages.create(
            model=model, max_tokens=max_tokens, temperature=temperature, system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()

    extra = {}
    if is_reasoning_model(model, provider):
        # Hidden reasoning tokens count toward max_tokens — leave headroom so the answer isn't cut off
        extra["extra_body"] = {"reasoning_effort": settings.LLM_REASONING_EFFORT}
        max_tokens += 1024
    elif provider == "gemini" and model.startswith("gemini-2.5-flash"):
        extra["extra_body"] = {"reasoning_effort": "none"}   # no hidden "thinking": faster, cheaper
    resp = await client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        max_tokens=max_tokens, temperature=temperature, **extra,
    )
    return (resp.choices[0].message.content or "").strip()


async def _try_provider(provider: str, prompt: str, system: str, max_tokens: int, temperature: float,
                        retries: int, has_backup: bool) -> str:
    """One provider, with its retry policy. Raises LLMRateLimited / LLMError on failure."""
    attempt, rate_limit_waits = 0, 0
    while True:
        try:
            text = await _call(provider, prompt, system, max_tokens, temperature)
            if not text:
                raise LLMError("Empty response from LLM")
            return text
        except LLMError as e:
            error: Exception = e
        except Exception as e:  # provider SDK errors
            error = e

        status = getattr(error, "status_code", None)
        if status == 429:
            wait = _retry_after(error)
            # With a backup available, don't make the reader wait — hand over right away
            if wait > MAX_RATE_LIMIT_SLEEP or has_backup:
                _paused_until[provider] = time.monotonic() + wait
                log.warning("%s rate limit: pausing it for %.0fs (provider said: %s)",
                            provider, wait, str(error)[:240])
                raise LLMRateLimited(wait) from error
            if rate_limit_waits < MAX_RATE_LIMIT_WAITS:
                rate_limit_waits += 1
                log.info("%s rate-limited; waiting %.1fs (%d/%d)", provider, wait, rate_limit_waits, MAX_RATE_LIMIT_WAITS)
                await asyncio.sleep(wait)
                continue

        log.warning("LLM call failed (%s/%s, attempt %d/%d): %s: %s", provider, settings.model_for(provider),
                    attempt + 1, retries + 1, type(error).__name__, str(error)[:300])
        if status in (400, 401, 403, 404) or attempt >= retries or has_backup:
            raise LLMError(f"{provider} failed: {type(error).__name__}") from error
        attempt += 1
        await asyncio.sleep(1.5 * attempt)


async def chat(
    prompt: str,
    system: str = "You are a helpful AI assistant.",
    max_tokens: int = 1500,
    temperature: float = 0.3,
    retries: int = 1,
) -> str:
    """Send a prompt to the first available provider and return the response text."""
    providers = settings.llm_providers
    if not providers:
        raise LLMNotConfigured(f"No API key set for LLM_PROVIDER={settings.LLM_PROVIDER} (and no backup)")

    last: Optional[LLMError] = None
    for i, provider in enumerate(providers):
        if _pause_left(provider):
            last = LLMRateLimited(_pause_left(provider))
            continue
        has_backup = any(not _pause_left(p) for p in providers[i + 1:])
        try:
            text = await _try_provider(provider, prompt, system, max_tokens, temperature, retries, has_backup)
            if i:
                log.info("Answered by backup provider %s", provider)
            return text
        except LLMError as e:
            last = e
    if all(_pause_left(p) for p in providers):
        raise LLMRateLimited(pause_remaining())
    raise last or LLMError("LLM call failed")


MAX_RATE_LIMIT_WAITS = 4
MAX_RATE_LIMIT_SLEEP = 60.0     # longer requested waits pause the provider instead
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
