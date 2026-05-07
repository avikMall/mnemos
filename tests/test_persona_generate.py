"""Tests for persona generation.

Two properties matter most:
1. Determinism: same (archetype, seed) → same persona every time.
2. Validity: every generated persona round-trips through the pydantic
   schema and respects the archetype's fact-key contract.
"""

from __future__ import annotations

from mnemos.personas.generate import (
    SUPPORTED_ARCHETYPES,
    generate_persona,
    generate_persona_set,
)
from mnemos.personas.templates import get_template
from mnemos.types import Archetype, Persona


def test_determinism_same_seed_same_persona() -> None:
    a = generate_persona(Archetype.EARLY_STAGE_FOUNDER, seed=12345)
    b = generate_persona(Archetype.EARLY_STAGE_FOUNDER, seed=12345)
    assert a == b


def test_different_seeds_produce_different_personas() -> None:
    a = generate_persona(Archetype.EARLY_STAGE_FOUNDER, seed=1)
    b = generate_persona(Archetype.EARLY_STAGE_FOUNDER, seed=2)
    assert a != b


def test_round_trip_through_json() -> None:
    p = generate_persona(Archetype.EARLY_STAGE_FOUNDER, seed=7)
    blob = p.model_dump_json()
    p2 = Persona.model_validate_json(blob)
    assert p2 == p


def test_all_template_facts_are_present() -> None:
    arch = Archetype.EARLY_STAGE_FOUNDER
    template = get_template(arch)
    expected_keys = {spec.key for spec in template.fact_specs}
    p = generate_persona(arch, seed=99)
    assert {f.key for f in p.facts} == expected_keys


def test_updates_target_known_facts() -> None:
    p = generate_persona(Archetype.EARLY_STAGE_FOUNDER, seed=42)
    fact_keys = {f.key for f in p.facts}
    for event in p.update_events:
        for change in event.fact_changes:
            assert change.key in fact_keys, (
                f"Update event {event.event_id} targets unknown fact "
                f"{change.key!r}; facts present: {fact_keys}"
            )


def test_update_session_ids_are_well_formed() -> None:
    p = generate_persona(Archetype.EARLY_STAGE_FOUNDER, seed=42, num_sessions=6)
    for event in p.update_events:
        # session_id like "s3"; must parse as int and be within bounds
        assert event.session_id.startswith("s")
        idx = int(event.session_id[1:])
        assert 1 <= idx <= 6


def test_supersession_links_are_set_when_update_targets_fact() -> None:
    p = generate_persona(Archetype.EARLY_STAGE_FOUNDER, seed=11)
    targeted_keys = {
        change.key
        for event in p.update_events
        for change in event.fact_changes
    }
    for fact in p.facts:
        if fact.key in targeted_keys:
            assert fact.superseded_by is not None, (
                f"Fact {fact.key!r} is targeted by an update but has no "
                f"superseded_by link"
            )
        else:
            assert fact.superseded_by is None


def test_generate_persona_set_returns_unique_ids() -> None:
    personas = generate_persona_set(
        Archetype.EARLY_STAGE_FOUNDER, seeds=range(10)
    )
    ids = [p.persona_id for p in personas]
    assert len(set(ids)) == len(ids)


def test_supported_archetypes_is_consistent() -> None:
    # Whatever's in templates.ARCHETYPES should be returned by SUPPORTED_ARCHETYPES.
    for arch in SUPPORTED_ARCHETYPES:
        # round-trip: should generate without raising
        generate_persona(arch, seed=0)
