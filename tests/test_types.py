"""Smoke tests for core data types.

These are intentionally light — schema-validation only, no network calls.
The point is to keep the SPEC.md ↔ types.py contract honest as we iterate.
"""

from datetime import datetime

from mnemos.types import (
    Archetype,
    Fact,
    Persona,
    Probe,
    Session,
    Trace,
    Turn,
    UpdateEvent,
)


def _toy_persona() -> Persona:
    return Persona(
        persona_id="founder_early_seed_007",
        archetype=Archetype.EARLY_STAGE_FOUNDER,
        static_profile={
            "name": "Asha Patel",
            "occupation": "Founder, stealth dev-tools startup",
            "location": "Brooklyn, NY",
        },
        facts=[
            Fact(key="co_founder_name", value="Marco Lin"),
            Fact(key="current_project", value="LLM-native testing harness"),
        ],
        update_events=[
            UpdateEvent(
                event_id="u1",
                session_id="s4",
                description="Marco leaves the company.",
                fact_changes=[
                    Fact(key="co_founder_name", value="(none — Marco departed)"),
                ],
            ),
        ],
        seed=42,
    )


def test_persona_round_trip() -> None:
    p = _toy_persona()
    blob = p.model_dump_json()
    p2 = Persona.model_validate_json(blob)
    assert p2 == p


def test_trace_minimal() -> None:
    s = Session(
        session_id="s1",
        timestamp=datetime(2025, 1, 10, 15, 0, 0),
        turns=[
            Turn(role="user", text="Hi, I'm Asha."),
            Turn(role="agent", text="Nice to meet you, Asha."),
        ],
        scheduled_disclosures=["co_founder_name"],
    )
    probe = Probe(
        probe_id="p1",
        axis="recall",
        after_session="s1",
        input="Remind me what I told you about my co-founder.",
        rubric_targets=["co_founder_name"],
    )
    t = Trace(
        trace_id="trace_001",
        persona_id="founder_early_seed_007",
        generator_version="v1",
        seed=42,
        sessions=[s],
        probes=[probe],
    )
    assert t.sessions[0].turns[0].role == "user"
    assert t.probes[0].axis == "recall"
