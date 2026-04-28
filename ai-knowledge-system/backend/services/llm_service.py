"""
LLMService — single place for all LLM calls.
Supports OpenAI and Anthropic; falls back to a mock when no key is set.
"""
from typing import Optional
from config import settings


def is_llm_configured() -> bool:
    return bool(
        (settings.LLM_PROVIDER == "openai" and settings.OPENAI_API_KEY)
        or (settings.LLM_PROVIDER == "anthropic" and settings.ANTHROPIC_API_KEY)
        or (settings.LLM_PROVIDER == "groq" and settings.GROQ_API_KEY)
    )


def is_mock_response(text: Optional[str]) -> bool:
    return bool(text and text.startswith("[MOCK RESPONSE"))


async def chat(
    prompt: str,
    system: str = "You are a helpful AI assistant.",
    max_tokens: int = 3000,
) -> str:
    """Send a prompt to the configured LLM and return the response text."""
    try:
        if settings.LLM_PROVIDER == "openai" and settings.OPENAI_API_KEY:
            return await _openai(prompt, system, max_tokens)
        if settings.LLM_PROVIDER == "anthropic" and settings.ANTHROPIC_API_KEY:
            return await _anthropic(prompt, system, max_tokens)
        if settings.LLM_PROVIDER == "groq" and settings.GROQ_API_KEY:
            return await _groq(prompt, system, max_tokens)
    except Exception as e:
        print(f"LLM error: {e}")
    return _mock(prompt)


async def _openai(prompt: str, system: str, max_tokens: int) -> str:
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    resp = await client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": prompt},
        ],
        max_tokens=max_tokens,
        temperature=0.3,
    )
    return resp.choices[0].message.content.strip()


async def _anthropic(prompt: str, system: str, max_tokens: int) -> str:
    import anthropic
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    resp = await client.messages.create(
        model=settings.LLM_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()


async def _groq(prompt: str, system: str, max_tokens: int) -> str:
    from groq import AsyncGroq
    # Significantly increased timeout for high-resolution reports
    client = AsyncGroq(api_key=settings.GROQ_API_KEY, timeout=20.0)
    resp = await client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": prompt},
        ],
        max_tokens=max_tokens,
        temperature=0.3,
    )
    return resp.choices[0].message.content.strip()



def _mock(prompt: str) -> str:
    return (
        "[MOCK RESPONSE — no LLM key configured] "
        "Set a supported LLM provider key (OPENAI_API_KEY, ANTHROPIC_API_KEY, or GROQ_API_KEY) in your .env file. "
        f"Prompt preview: {prompt[:100]}..."
    )
