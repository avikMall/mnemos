"""Tests for trace generation orchestration.

We use the DeterministicMockLLMClient so these tests exercise the
session loop, end-session handling, and trace assembly without needing
an Anthropic API key.

What we're testing here is the orchestration, not the realism of the
conversation. Realism testing is a manual review pass on a sample of
traces produced with the real Anthropic client (see NEXT_STEPS.md).
"""

from __future__ import annotations

from datetime import datetime, timezone

from mnemos.personas.generate import generate_persona
from mnemos.traces.generate import TraceGenConfig, generate_trace
from mnemos.traces.llm import DeterministicMockLLMClient
from mnemos.types import Archetype, Trace


def _mock_client(end_after: int = 4) -> DeterministicMockLLMClient:
    return DeterministicMockLLMClient(end_after_user_turns=end_after)


def test_generates_full_session_count() -> None:
    p = generate_persona(Archetype.EARLY_STAGE_FOUNDER, seed=2)
    cfg = TraceGenConfig(num_sessions=4, max_user_turns_per_session=6,
                         min_user_turns_per_session=2)
    trace = generate_trace(
        p,
        config=cfg,
        user_sim_client=_mock_client(end_after=3),
        agent_client=_mock_client(end_after=3),
        base_timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    assert len(trace.sessions) == 4
    for i, session in enumerate(trace.sessions, 1):
        assert session.session_id == f"s{i}"


def test_end_session_token_terminates_session() -> None:
    p = generate_persona(Archetype.EARLY_STAGE_FOUNDER, seed=2)
    cfg = TraceGenConfig(num_sessions=2, max_user_turns_per_session=20,
                         min_user_turns_per_session=2)
    trace = generate_trace(
        p,
        config=cfg,
        user_sim_client=_mock_client(end_after=3),
        agent_client=_mock_client(end_after=3),
    )
    # The mock signals end after `end_after` user turns. We expect each
    # session to stop near that boundary, well below the 20-turn budget.
    for session in trace.sessions:
        user_turns = [t for t in session.turns if t.role == "user"]
        assert 3 <= len(user_turns) <= 4


def test_min_turns_floor_prevents_premature_end() -> None:
    p = generate_persona(Archetype.EARLY_STAGE_FOUNDER, seed=2)
    cfg = TraceGenConfig(num_sessions=1, max_user_turns_per_session=20,
                         min_user_turns_per_session=5)
    trace = generate_trace(
        p,
        config=cfg,
        # Mock tries to end after 1 turn, but min-floor forces 5.
        user_sim_client=_mock_client(end_after=1),
        agent_client=_mock_client(end_after=1),
    )
    user_turns = [t for t in trace.sessions[0].turns if t.role == "user"]
    assert len(user_turns) >= 5


def test_turn_budget_caps_runaway_session() -> None:
    p = generate_persona(Archetype.EARLY_STAGE_FOUNDER, seed=2)
    cfg = TraceGenConfig(num_sessions=1, max_user_turns_per_session=4,
                         min_user_turns_per_session=2)
    trace = generate_trace(
        p,
        config=cfg,
        user_sim_client=_mock_client(end_after=99),  # never ends
        agent_client=_mock_client(end_after=99),
    )
    user_turns = [t for t in trace.sessions[0].turns if t.role == "user"]
    assert len(user_turns) == 4


def test_scheduled_disclosures_recorded_per_session() -> None:
    p = generate_persona(Archetype.EARLY_STAGE_FOUNDER, seed=2)
    cfg = TraceGenConfig(num_sessions=4, max_user_turns_per_session=4,
                         min_user_turns_per_session=2)
    trace = generate_trace(
        p,
        config=cfg,
        user_sim_client=_mock_client(end_after=2),
        agent_client=_mock_client(end_after=2),
    )
    # Sessions 1..3 should carry disclosure plans; session 4 should be empty.
    assert len(trace.sessions[0].scheduled_disclosures) > 0
    assert len(trace.sessions[1].scheduled_disclosures) > 0
    assert len(trace.sessions[2].scheduled_disclosures) > 0
    assert trace.sessions[3].scheduled_disclosures == []


def test_scheduled_updates_recorded_in_correct_session() -> None:
    p = generate_persona(Archetype.EARLY_STAGE_FOUNDER, seed=2)
    cfg = TraceGenConfig(num_sessions=6, max_user_turns_per_session=4,
                         min_user_turns_per_session=2)
    trace = generate_trace(
        p,
        config=cfg,
        user_sim_client=_mock_client(end_after=2),
        agent_client=_mock_client(end_after=2),
    )
    # Persona seed=2 has round_closes@s4 and cofounder_departs@s6
    assert "round_closes" in trace.sessions[3].scheduled_updates
    assert "cofounder_departs" in trace.sessions[5].scheduled_updates
    # Non-update sessions should be empty
    assert trace.sessions[0].scheduled_updates == []
    assert trace.sessions[1].scheduled_updates == []


def test_probes_attached_to_trace() -> None:
    p = generate_persona(Archetype.EARLY_STAGE_FOUNDER, seed=2)
    cfg = TraceGenConfig(num_sessions=6, max_user_turns_per_session=4,
                         min_user_turns_per_session=2)
    trace = generate_trace(
        p,
        config=cfg,
        user_sim_client=_mock_client(end_after=2),
        agent_client=_mock_client(end_after=2),
    )
    assert len(trace.probes) > 0
    axes = {pr.axis for pr in trace.probes}
    assert axes == {"recall", "consolidation", "update"}


def test_trace_round_trip_through_json() -> None:
    p = generate_persona(Archetype.EARLY_STAGE_FOUNDER, seed=2)
    cfg = TraceGenConfig(num_sessions=2, max_user_turns_per_session=4,
                         min_user_turns_per_session=2)
    trace = generate_trace(
        p,
        config=cfg,
        user_sim_client=_mock_client(end_after=2),
        agent_client=_mock_client(end_after=2),
    )
    blob = trace.model_dump_json()
    trace2 = Trace.model_validate_json(blob)
    assert trace2 == trace


def test_alternating_user_agent_turns() -> None:
    p = generate_persona(Archetype.EARLY_STAGE_FOUNDER, seed=2)
    cfg = TraceGenConfig(num_sessions=1, max_user_turns_per_session=4,
                         min_user_turns_per_session=2)
    trace = generate_trace(
        p,
        config=cfg,
        user_sim_client=_mock_client(end_after=99),
        agent_client=_mock_client(end_after=99),
    )
    roles = [t.role for t in trace.sessions[0].turns]
    # Always starts with user, alternates strictly
    for i, role in enumerate(roles):
        assert role == ("user" if i % 2 == 0 else "agent")


def test_end_token_stripped_from_user_turn_text() -> None:
    p = generate_persona(Archetype.EARLY_STAGE_FOUNDER, seed=2)
    cfg = TraceGenConfig(num_sessions=1, max_user_turns_per_session=8,
                         min_user_turns_per_session=2)
    trace = generate_trace(
        p,
        config=cfg,
        user_sim_client=_mock_client(end_after=3),
        agent_client=_mock_client(end_after=3),
    )
    for t in trace.sessions[0].turns:
        assert "[END_SESSION]" not in t.text
