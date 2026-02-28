"""Supermemory integration — persona bootstrapping, context retrieval, and memory storage."""

from __future__ import annotations

import os

from dotenv import load_dotenv
from openai import OpenAI
from supermemory import Supermemory

load_dotenv()

# ── Lazy-initialised clients (avoids crash when env vars are absent) ─────────
_sm_client: Supermemory | None = None
_oai_client: OpenAI | None = None


def _get_sm_client() -> Supermemory:
    global _sm_client
    if _sm_client is None:
        _sm_client = Supermemory(api_key=os.getenv("SUPERMEMORY_API_KEY"))
    return _sm_client


def _get_oai_client() -> OpenAI:
    global _oai_client
    if _oai_client is None:
        _oai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _oai_client

# ── Prompt used to expand a raw persona into structured facts + memories ─────
_BOOTSTRAP_SYSTEM_PROMPT = """\
You are a persona-expansion engine.  Given a raw, highly specific persona description for a
synthetic agent, produce TWO clearly-separated sections:

## Static Facts
Bullet-pointed list of immutable biographical facts (name, age, occupation,
personality traits, core beliefs, etc.) This will also include the synth's talking style, personality, smartness level, etc.

## Seed Memories
A set of 5-10 first-person memory snippets that this persona would plausibly
have.  Each memory should be a short paragraph written from the persona's
point-of-view, referencing concrete events, emotions, or decisions.  The
richer and more specific these are, the more lifelike the agent will behave.

Be creative but stay strictly consistent with the supplied persona.  Do NOT
add facts that contradict the description. Be Highly detailed, avoid vage values and descriptions.
"""


def bootstrap_persona(
    synth_id: str,
    persona_prompt: str,
    model: str = "gpt-4o",
) -> str:
    """Expand a raw persona into structured facts + seed memories, then store
    them in Supermemory so the synth can recall them in future turns.

    Parameters
    ----------
    synth_id : str
        Used as the Supermemory ``container_tag``.
    persona_prompt : str
        The raw, potentially brief persona description provided by the caller.
        Richer inputs (historic conversations, past decisions, preferences)
        yield more lifelike synths.
    model : str
        OpenAI model to use for the expansion step.

    Returns
    -------
    str
        The expanded persona text that was stored.
    """

    # 1. Use OpenAI to expand the persona into structured content
    response = _get_oai_client().chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _BOOTSTRAP_SYSTEM_PROMPT},
            {"role": "user", "content": persona_prompt},
        ],
        temperature=0.9,
    )
    expanded_persona: str = response.choices[0].message.content or ""

    # 2. Store the expanded persona in Supermemory for long-term recall
    _get_sm_client().add(
        content=expanded_persona,
        container_tag=synth_id,
    )

    return expanded_persona


def get_synth_context(synth_id: str, current_situation: str) -> str:
    """Retrieve memory-enriched context for a synth from Supermemory.

    Calls ``sm_client.profile()`` which searches the vector-graph database
    for memories relevant to *current_situation* scoped to *synth_id*.

    Returns a formatted context block with three sections:
    ``[YOUR PERSONALITY]``, ``[YOUR CURRENT STATE]``, ``[RELEVANT MEMORIES]``.
    """

    profile_data = _get_sm_client().profile(
        container_tag=synth_id,
        q=current_situation,
    )

    static_facts = "\n".join(profile_data.profile.static)
    dynamic_context = "\n".join(profile_data.profile.dynamic)
    relevant_memories = "\n".join(
        r.get("memory", "") for r in profile_data.search_results.results
    )

    return (
        f"[YOUR PERSONALITY]:\n{static_facts}\n\n"
        f"[YOUR CURRENT STATE]:\n{dynamic_context}\n\n"
        f"[RELEVANT MEMORIES]:\n{relevant_memories}"
    )


def store_memory(synth_id: str, content: str) -> None:
    """Persist a piece of content into Supermemory for future recall.

    Called after every cognitive turn so the synth remembers its actions.
    """

    _get_sm_client().add(
        content=content,
        container_tag=synth_id,
    )
