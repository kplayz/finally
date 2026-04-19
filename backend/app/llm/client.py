"""Live LLM call via LiteLLM → OpenRouter → Cerebras.

Follows the cerebras-inference skill: structured-output mode with the
Cerebras provider routed through OpenRouter.
"""

from __future__ import annotations

import asyncio
import logging

from .schema import LLMOutput

log = logging.getLogger(__name__)

EXTRA_BODY = {"provider": {"order": ["cerebras"]}}


async def call_llm(messages: list[dict], model: str) -> LLMOutput:
    """Run the completion off the event loop and return a validated LLMOutput."""
    from litellm import completion  # imported lazily so tests don't need it

    def _do() -> str:
        response = completion(
            model=model,
            messages=messages,
            response_format=LLMOutput,
            reasoning_effort="low",
            extra_body=EXTRA_BODY,
        )
        return response.choices[0].message.content  # type: ignore[no-any-return]

    raw = await asyncio.to_thread(_do)
    return LLMOutput.model_validate_json(raw)
