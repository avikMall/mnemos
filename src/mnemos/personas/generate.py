"""Deterministic persona generation.

`generate_persona(archetype, seed)` is a pure function: same inputs always
produce the same persona. We use Python's `random.Random(seed)` rather
than the global RNG so concurrent generation is safe and seeds are scoped.

The generator picks values from the archetype template's pools, schedules
zero, one, or two update events, and assigns the session in which each
update fires. The agent under test never sees this object; only the
trace generator and evaluator do.
"""

from __future__ import annotations

import random
from typing import Iterable

from mnemos.personas.templates import (
    ARCHETYPES,
    ArchetypeTemplate,
    UpdateSpec,
    get_template,
)
from mnemos.types import (
    Archetype,
    Fact,
    Persona,
    UpdateEvent,
)


def generate_persona(
    archetype: Archetype,
    seed: int,
    *,
    num_sessions: int = 6,
    max_updates: int = 2,
) -> Persona:
    """Generate a persona deterministically from (archetype, seed).

    Args:
        archetype: which archetype to draw from.
        seed: integer seed; same seed → same persona.
        num_sessions: total sessions the persona will appear in. Updates
            are only scheduled into sessions whose index is ≥ each
            UpdateSpec's `earliest_session_index`.
        max_updates: cap on how many update events the persona has. v1
            uses up to 2 to keep traces manageable; v2 may parameterize
            this further.

    Returns:
        A `Persona` whose `seed` field is preserved so the trace generator
        can derive its own RNG from it.
    """
    template = get_template(archetype)
    rng = random.Random(seed)

    static_profile = _pick_static_profile(template, rng)
    facts = _pick_facts(template, rng)
    update_events = _schedule_updates(
        template, rng, num_sessions=num_sessions, max_updates=max_updates
    )

    persona_id = _persona_id(archetype, seed)

    # When updates supersede a fact, link them so the evaluator can reason
    # about chronological state.
    facts = _link_supersession(facts, update_events)

    return Persona(
        persona_id=persona_id,
        archetype=archetype,
        static_profile=static_profile,
        facts=facts,
        update_events=update_events,
        seed=seed,
    )


def generate_persona_set(
    archetype: Archetype,
    seeds: Iterable[int],
    **kwargs,
) -> list[Persona]:
    """Generate many personas from one archetype, deterministically."""
    return [generate_persona(archetype, s, **kwargs) for s in seeds]


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _persona_id(archetype: Archetype, seed: int) -> str:
    return f"{archetype.value}__seed_{seed:06d}"


def _pick_static_profile(
    template: ArchetypeTemplate, rng: random.Random
) -> dict[str, str]:
    return {
        key: rng.choice(pool)
        for key, pool in template.static_profile_pools.items()
    }


def _pick_facts(template: ArchetypeTemplate, rng: random.Random) -> list[Fact]:
    return [
        Fact(key=spec.key, value=rng.choice(spec.value_pool))
        for spec in template.fact_specs
    ]


def _schedule_updates(
    template: ArchetypeTemplate,
    rng: random.Random,
    *,
    num_sessions: int,
    max_updates: int,
) -> list[UpdateEvent]:
    """Pick which update events fire, and in which session.

    We sample without replacement to avoid two updates targeting the same
    fact key in one persona — that would create rubric ambiguity for the
    Update axis in v1. (v2 may relax this.)
    """
    candidates: list[UpdateSpec] = list(template.update_specs)
    rng.shuffle(candidates)

    n_updates = rng.randint(0, min(max_updates, len(candidates)))
    chosen = candidates[:n_updates]

    # Enforce one update per fact key.
    seen_targets: set[str] = set()
    chosen = [u for u in chosen if not (u.target_fact_key in seen_targets or seen_targets.add(u.target_fact_key))]

    events: list[UpdateEvent] = []
    used_sessions: set[int] = set()
    for spec in chosen:
        # earliest_session_index is 1-indexed in the spec; convert to s{N}.
        valid_sessions = [
            i for i in range(spec.earliest_session_index, num_sessions + 1)
            if i not in used_sessions
        ]
        if not valid_sessions:
            continue
        session_idx = rng.choice(valid_sessions)
        used_sessions.add(session_idx)

        new_value = rng.choice(spec.new_value_pool)
        events.append(
            UpdateEvent(
                event_id=spec.event_id,
                session_id=f"s{session_idx}",
                description=_format_description(spec, new_value),
                fact_changes=[Fact(key=spec.target_fact_key, value=new_value)],
            )
        )
    # Stable order by session_id for readable JSON.
    events.sort(key=lambda e: e.session_id)
    return events


def _format_description(spec: UpdateSpec, new_value: str) -> str:
    # The {old} placeholder is filled in by the trace generator at runtime
    # using the persona's actual prior value; we leave it as a token here.
    return spec.description_template.replace("{new}", new_value)


def _link_supersession(
    facts: list[Fact], updates: list[UpdateEvent]
) -> list[Fact]:
    """Stamp `superseded_by` on facts that an update event will replace."""
    update_keys = {
        change.key
        for event in updates
        for change in event.fact_changes
    }
    return [
        f.model_copy(update={"superseded_by": _first_event_for_key(updates, f.key)})
        if f.key in update_keys
        else f
        for f in facts
    ]


def _first_event_for_key(events: list[UpdateEvent], key: str) -> str | None:
    for e in events:
        if any(c.key == key for c in e.fact_changes):
            return e.event_id
    return None


# Public surface: discover what's available without importing templates.
SUPPORTED_ARCHETYPES: list[Archetype] = list(ARCHETYPES.keys())
