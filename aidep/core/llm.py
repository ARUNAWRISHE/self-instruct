"""
LiteLLM-based, model-provider-independent LLM client.

Supports:
    openai/gpt-4o-mini
    gemini/gemini-1.5-flash
    openrouter/openai/gpt-4o
    mock  (offline dry-run — no API key required)
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_MOCK_RESPONSES = {
    "instruction": (
        "1. Write a Python function that checks if a string is a palindrome.\n"
        "2. Explain the difference between supervised and unsupervised learning.\n"
        "3. Draft a professional email declining a job offer politely.\n"
        "4. Calculate the compound interest for $10,000 at 6% for 5 years.\n"
        "5. Summarize the key causes of World War I in under 150 words."
    ),
    "example": (
        "Constraints: None\n"
        "Input: None\n"
        "Output: Here is a Python palindrome checker:\n"
        "```python\n"
        "def is_palindrome(s: str) -> bool:\n"
        "    cleaned = s.lower().replace(' ', '')\n"
        "    return cleaned == cleaned[::-1]\n"
        "```"
    ),
    "analysis": (
        "Task Type: Coding\n"
        "Category: coding\n"
        "Domain: Software Engineering\n"
        "Subdomain: Algorithms\n"
        "Difficulty: Medium\n"
        "Reasoning Level: Medium\n"
        "Expected Output Type: Code\n"
        "Complexity: 0.45"
    ),
    "default": "This is a mock response from the AIDEP offline dry-run generator.",
}


def _mock_generate(prompt: str) -> str:
    """Return a realistic mock response based on prompt content."""
    lower = prompt.lower()
    if any(k in lower for k in ["instruction", "generate", "diverse"]):
        return _MOCK_RESPONSES["instruction"]
    if any(k in lower for k in ["input", "output", "constraints", "example"]):
        return _MOCK_RESPONSES["example"]
    if any(k in lower for k in ["category", "classify", "analyze", "task type"]):
        return _MOCK_RESPONSES["analysis"]
    return _MOCK_RESPONSES["default"]


class LLMClient:
    """
    Model-provider-independent LLM client backed by LiteLLM.

    Args:
        model: LiteLLM model string, e.g. "openai/gpt-4o-mini",
               "gemini/gemini-1.5-flash", or "mock".
        temperature: Sampling temperature.
        max_tokens: Maximum tokens in completion.
        timeout: Request timeout in seconds.
    """

    def __init__(
        self,
        model: str = "mock",
        temperature: float = 0.7,
        max_tokens: int = 2048,
        timeout: int = 120,
        api_keys: Optional[dict] = None,
    ):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self._is_mock = model.lower() == "mock"

        if not self._is_mock and api_keys:
            # Propagate API keys to env for LiteLLM to pick up
            for env_var, key_value in api_keys.items():
                if key_value:
                    os.environ[env_var] = key_value

    def generate(
        self,
        prompt: str,
        system_prompt: str = "You are a helpful assistant.",
    ) -> str:
        """Generate a response for the given prompt."""
        if self._is_mock:
            logger.debug("Mock mode: returning cached response.")
            return _mock_generate(prompt)

        try:
            import litellm  # noqa: PLC0415 — lazy import

            response = litellm.completion(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                timeout=self.timeout,
            )
            return response.choices[0].message.content.strip()
        except Exception as exc:
            logger.warning(
                "LiteLLM call failed (%s). Falling back to mock generator.", exc
            )
            return _mock_generate(prompt)

    @classmethod
    def from_settings(cls, settings) -> "LLMClient":
        """Construct an LLMClient from app Settings."""
        return cls(
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            timeout=settings.llm_timeout,
            api_keys={
                "OPENAI_API_KEY": settings.openai_api_key,
                "GEMINI_API_KEY": settings.gemini_api_key,
                "OPENROUTER_API_KEY": settings.openrouter_api_key,
            },
        )
