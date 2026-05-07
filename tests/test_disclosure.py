"""Tests for disclosure-plan construction."""

from __future__ import annotations

from mnemos.personas.generate import generate_persona
from mnemos.traces.disclosure import (
    V1_DISCLOSURE_ORDER,
    all_disclosed_keys_through,
    build_disclosure_plan,
)
from mnemos.types import Archetype


def test_plan_length_matches_num_sessions() -> None:
    p = generate_persona(Archetype.EARLY_STAGE_FOUNDER, seed=1)
    plan = build_disclosure_plan(p, num_sessions=6)
    assert len(plan) == 6


def test_plan_only_uses_present_fact_keys() -> None:
    p = generate_persona(Archetype.EARLY_STAGE_FOUNDER, seed=1)
    plan = build_disclosure_plan(p, num_sessions=6)
    persona_keys = {f.key for f in p.facts}
    for sess in plan:
        for key in sess:
            assert key in persona_keys


def test_late_sessions_have_no_new_disclosures() -> None:
    p = generate_persona(Archetype.EARLY_STAGE_FOUNDER, seed=1)
    plan = build_disclosure_plan(p, num_sessions=6)
    # v1 schedules all introductions in the first len(V1_DISCLOSURE_ORDER) sessions
    for sess in plan[len(V1_DISCLOSURE_ORDER):]:
        assert sess == []


def test_all_facts_disclosed_by_end_of_intro_window() -> None:
    p = generate_persona(Archetype.EARLY_STAGE_FOUNDER, seed=1)
    plan = build_disclosure_plan(p, num_sessions=6)
    disclosed = all_disclosed_keys_through(plan, len(V1_DISCLOSURE_ORDER))
    persona_keys = {f.key for f in p.facts}
    assert persona_keys == disclosed


def test_short_trace_truncates_plan_cleanly() -> None:
    p = generate_persona(Archetype.EARLY_STAGE_FOUNDER, seed=1)
    plan = build_disclosure_plan(p, num_sessions=2)
    # First 2 entries of V1_DISCLOSURE_ORDER are present, no later ones
    assert len(plan) == 2
    expected_first_session = [
        k for k in V1_DISCLOSURE_ORDER[0] if k in {f.key for f in p.facts}
    ]
    assert plan[0] == expected_first_session


def test_all_disclosed_keys_through_zero_returns_empty() -> None:
    p = generate_persona(Archetype.EARLY_STAGE_FOUNDER, seed=1)
    plan = build_disclosure_plan(p, num_sessions=6)
    assert all_disclosed_keys_through(plan, 0) == set()
