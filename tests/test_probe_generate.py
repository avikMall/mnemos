"""Tests for probe generation.

Properties under test:
1. Determinism: same persona → same probe set.
2. Coverage: at least one probe per axis when the persona has updates.
3. Update probes are anchored to update events that actually fired.
4. Update probe latency bins land on valid sessions.
5. Probe IDs are unique within a persona.
6. JSON round-trip via pydantic.
"""

from __future__ import annotations

from mnemos.personas.generate import generate_persona
from mnemos.probes.generate import generate_probes
from mnemos.types import Archetype, Probe


# Seeds chosen because they exercise different update configurations:
# - SEED_NO_UPDATES: a persona with zero update events.
# - SEED_UPDATES_FIRE: a persona with both round_closes and cofounder_departs.
SEED_NO_UPDATES = 42  # confirmed in session: empty update_events
SEED_UPDATES_FIRE = 2  # confirmed in session: round_closes (s4) + cofounder_departs (s6)


def test_determinism_same_persona_same_probes() -> None:
    p = generate_persona(Archetype.EARLY_STAGE_FOUNDER, seed=SEED_UPDATES_FIRE)
    a = generate_probes(p, num_sessions=6)
    b = generate_probes(p, num_sessions=6)
    assert a == b


def test_persona_without_updates_has_only_recall_and_consolidation() -> None:
    p = generate_persona(Archetype.EARLY_STAGE_FOUNDER, seed=SEED_NO_UPDATES)
    assert p.update_events == []  # confirms our seed assumption
    probes = generate_probes(p, num_sessions=6)
    axes = {pr.axis for pr in probes}
    assert "update" not in axes, (
        "A persona with no update events should not generate update probes; "
        f"got axes={axes}"
    )
    assert "recall" in axes
    assert "consolidation" in axes


def test_persona_with_updates_has_update_probes() -> None:
    p = generate_persona(Archetype.EARLY_STAGE_FOUNDER, seed=SEED_UPDATES_FIRE)
    assert p.update_events, "seed assumption broke — pick a new SEED_UPDATES_FIRE"
    probes = generate_probes(p, num_sessions=6)
    update_probes = [pr for pr in probes if pr.axis == "update"]
    assert len(update_probes) > 0


def test_update_probes_reference_real_events() -> None:
    p = generate_persona(Archetype.EARLY_STAGE_FOUNDER, seed=SEED_UPDATES_FIRE)
    fired_event_ids = {e.event_id for e in p.update_events}
    probes = generate_probes(p, num_sessions=6)
    for pr in probes:
        if pr.axis != "update":
            continue
        ev_id = pr.metadata.get("update_event_id")
        assert ev_id in fired_event_ids, (
            f"update probe {pr.probe_id!r} references event {ev_id!r}, "
            f"but only {fired_event_ids} actually fired"
        )


def test_update_probe_latency_bins_land_on_valid_sessions() -> None:
    p = generate_persona(Archetype.EARLY_STAGE_FOUNDER, seed=SEED_UPDATES_FIRE)
    probes = generate_probes(p, num_sessions=6)
    for pr in probes:
        if pr.axis != "update":
            continue
        idx = int(pr.after_session[1:])
        assert 1 <= idx <= 6, (
            f"update probe {pr.probe_id!r} scheduled on out-of-range "
            f"session {pr.after_session!r}"
        )
        # The probe must come strictly after the update session.
        update_idx = int(pr.metadata["update_session"][1:])
        assert idx > update_idx, (
            f"update probe {pr.probe_id!r} on session {pr.after_session} "
            f"is not strictly after update session {pr.metadata['update_session']}"
        )


def test_probe_ids_unique_within_persona() -> None:
    p = generate_persona(Archetype.EARLY_STAGE_FOUNDER, seed=SEED_UPDATES_FIRE)
    probes = generate_probes(p, num_sessions=6)
    ids = [pr.probe_id for pr in probes]
    assert len(ids) == len(set(ids))


def test_probe_round_trip_through_json() -> None:
    p = generate_persona(Archetype.EARLY_STAGE_FOUNDER, seed=SEED_UPDATES_FIRE)
    for pr in generate_probes(p, num_sessions=6):
        blob = pr.model_dump_json()
        pr2 = Probe.model_validate_json(blob)
        assert pr2 == pr


def test_recall_probes_have_rubric_targets_or_are_negative() -> None:
    p = generate_persona(Archetype.EARLY_STAGE_FOUNDER, seed=SEED_UPDATES_FIRE)
    probes = generate_probes(p, num_sessions=6)
    for pr in probes:
        if pr.axis != "recall":
            continue
        is_negative = pr.metadata["template_id"].startswith("recall_negative_")
        if not is_negative:
            assert pr.rubric_targets, (
                f"recall probe {pr.probe_id!r} has empty rubric_targets "
                f"and is not a negative-recall template"
            )


def test_short_trace_clips_late_latency_probes() -> None:
    """A short trace shouldn't generate update probes whose target session
    would exceed num_sessions."""
    p = generate_persona(Archetype.EARLY_STAGE_FOUNDER, seed=SEED_UPDATES_FIRE)
    short_probes = generate_probes(p, num_sessions=4)
    for pr in short_probes:
        idx = int(pr.after_session[1:])
        assert idx <= 4, (
            f"probe {pr.probe_id!r} schedules at session {idx} for a "
            f"trace of length 4"
        )


def test_consolidate_what_changed_surfaces_update_event_keys() -> None:
    p = generate_persona(Archetype.EARLY_STAGE_FOUNDER, seed=SEED_UPDATES_FIRE)
    probes = generate_probes(p, num_sessions=6)
    target = next(
        pr for pr in probes
        if pr.metadata["template_id"] == "consolidate_what_changed"
    )
    fired_event_ids = {e.event_id for e in p.update_events}
    targets = set(target.rubric_targets)
    for ev_id in fired_event_ids:
        assert f"update.{ev_id}" in targets
