"""Deterministic per-session disclosure plan.

Decides which fact keys the user simulator should bring up in each
session. v1 strategy: introduce facts in the early sessions in a fixed
schedule, leave the later sessions for "deeper" / follow-up
conversations and any update events. Update events are not part of
the disclosure plan — they're communicated via `Persona.update_events`
directly to the simulator at the appropriate session.

Why this lives here, not in `personas.generate`
-----------------------------------------------

Disclosure scheduling is a property of how a *trace* unfolds, not of
the underlying persona. The same persona could be re-traced with a
different disclosure cadence (e.g., to test memory under denser vs.
sparser disclosure). Keeping the plan here lets us swap strategies
without rewriting persona generation.
"""

from __future__ import annotations

from mnemos.types import Persona


# v1 plan: introduce facts in this fixed order across the first three
# sessions, then leave the remainder open. The order is chosen so the
# first session establishes who-they-are (project + co-founder), the
# second session goes into goals (fundraising + hiring), and the third
# surfaces the emotional layer.
V1_DISCLOSURE_ORDER: tuple[tuple[str, ...], ...] = (
    ("current_project", "co_founder_name"),
    ("fundraising_stage", "hiring_priority"),
    ("emotional_undercurrent",),
)


def build_disclosure_plan(persona: Persona, num_sessions: int) -> list[list[str]]:
    """Return per-session lists of fact keys to disclose.

    Args:
        persona: source of fact keys (only keys present on the persona
            are returned, so a template that omits a fact won't crash
            the plan).
        num_sessions: trace length. Plans for sessions 1..num_sessions
            inclusive.

    Returns:
        A list of length `num_sessions`. Each element is the fact keys
        the simulator should aim to disclose in that session.
    """
    persona_fact_keys = {f.key for f in persona.facts}
    plan: list[list[str]] = []
    for session_idx in range(num_sessions):
        if session_idx < len(V1_DISCLOSURE_ORDER):
            keys = [
                k for k in V1_DISCLOSURE_ORDER[session_idx]
                if k in persona_fact_keys
            ]
        else:
            keys = []
        plan.append(keys)
    return plan


def all_disclosed_keys_through(
    plan: list[list[str]], session_idx: int
) -> set[str]:
    """Return all keys disclosed in sessions 1..session_idx (inclusive).

    Used to remind the simulator what's already on the table when
    generating a later session, so it doesn't reintroduce facts as if
    they were new.
    """
    if session_idx < 1:
        return set()
    return {k for sess in plan[:session_idx] for k in sess}
