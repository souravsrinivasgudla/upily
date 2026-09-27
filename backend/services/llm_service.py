"""
LLMService — single place for all LLM calls (Groq, OpenAI or Anthropic).

`chat()` raises instead of returning placeholder text, so callers can tell
"no key configured" apart from "provider failed" and show the right message.
"""
import asyncio
import logging

from config import settings

log = logging.getLogger(__name__)


class LLMError(Exception):
    """The provider call failed (timeout, rate limit, bad model, …)."""


class LLMNotConfigured(LLMError):
    """No API key is set for the selected LLM_PROVIDER."""


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
    if not settings.llm_configured:
        raise LLMNotConfigured(
            f"No API key set for LLM_PROVIDER={settings.LLM_PROVIDER}"
        )

    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            text = await _call(prompt, system, max_tokens, temperature)
            if not text:
                raise LLMError("Empty response from LLM")
            return text
        except LLMError as e:
            last_error = e
        except Exception as e:  # provider SDK errors
            last_error = e
        log.warning("LLM call failed (attempt %d/%d, %s/%s): %s: %s",
                    attempt + 1, retries + 1, settings.LLM_PROVIDER, settings.llm_model,
                    type(last_error).__name__, str(last_error)[:300])
        if getattr(last_error, "status_code", None) in (400, 401, 403, 404):
            break   # bad key / unknown model — retrying won't help
        if attempt < retries:
            await asyncio.sleep(1.5 * (attempt + 1))

    raise LLMError(f"LLM call failed: {type(last_error).__name__}") from last_error
