"""GOD — the omniscient observer that can analyze a completed simulation."""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI
from prompt import build_god_system_prompt

load_dotenv()

_oai_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _oai_client
    if _oai_client is None:
        _oai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _oai_client


class God:
    """Omniscient LLM that reads the full simulation transcript and answers
    meta-questions about synth behavior, adoption, and sentiment.

    Usage
    -----
    >>> god = God(environment)
    >>> answer = god.ask("What themes emerged in this simulation?")
    """

    def __init__(self, environment: Any, model: str = "gpt-4o") -> None:
        self.env = environment
        self.model = model
        self._chat_history: list[dict] = []

    def ask(self, question: str) -> str:
        """Ask GOD a question about the simulation."""
        transcript = self.env.get_transcript()
        stats = self.env.get_stats()

        # Build participant summary
        synth_details = "\n".join(
            f"- {s.synth_name} ({s.synth_id}): {s.persona_prompt[:200]}... | "
            f"Tools: {s.allowed_tools}"
            for s in self.env.synths.values()
        )

        # Build artifacts summary for context
        from artifacts import artifact_context_block
        artifacts_summary = artifact_context_block(self.env.artifacts, max_chars=10000)

        system_prompt = build_god_system_prompt(
            environment_objective=f"{self.env.objective}\n\nARTIFACTS:\n{artifacts_summary}",
            synth_details=synth_details,
            stats=stats,
            transcript=transcript,
        )

        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(self._chat_history)
        messages.append({"role": "user", "content": question})

        response = _get_client().chat.completions.create(
            model=self.model,
            messages=messages,
        )

        answer = response.choices[0].message.content or ""

        # Maintain conversational context for follow-ups
        self._chat_history.append({"role": "user", "content": question})
        self._chat_history.append({"role": "assistant", "content": answer})

        return answer
