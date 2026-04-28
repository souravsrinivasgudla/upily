"""
Base Agent — shared LLM call logic for all agents.
"""
from typing import Optional
from config import settings


class BaseAgent:
    """All agents inherit from this; provides a unified LLM interface."""

    def __init__(self, system_prompt: str = "You are a helpful AI assistant."):
        self.system_prompt = system_prompt

    async def llm(self, prompt: str, max_tokens: int = 1500) -> str:
        """Call the configured LLM and return the response text."""
        try:
            if settings.LLM_PROVIDER == "openai" and settings.OPENAI_API_KEY:
                return await self._openai(prompt, max_tokens)
            elif settings.LLM_PROVIDER == "anthropic" and settings.ANTHROPIC_API_KEY:
                return await self._anthropic(prompt, max_tokens)
            else:
                return self._mock_response(prompt)
        except Exception as e:
            print(f"LLM error ({self.__class__.__name__}): {e}")
            return ""

    async def _openai(self, prompt: str, max_tokens: int) -> str:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        resp = await client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
            temperature=0.3,
        )
        return resp.choices[0].message.content.strip()

    async def _anthropic(self, prompt: str, max_tokens: int) -> str:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        resp = await client.messages.create(
            model=settings.LLM_MODEL,
            max_tokens=max_tokens,
            system=self.system_prompt,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip()

    def _mock_response(self, prompt: str) -> str:
        """Fallback when no API key is configured — returns a placeholder."""
        return (
            "[MOCK] No LLM API key configured. "
            "Set OPENAI_API_KEY or ANTHROPIC_API_KEY in .env to enable AI features. "
            f"Received prompt starting with: {prompt[:80]}..."
        )
