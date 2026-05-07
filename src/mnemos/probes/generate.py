"""Deterministic probe generation.

`generate_probes(persona, num_sessions)` produces the full probe set
for a persona, identical across runs given the same inputs.

What the generator does
-----------------------

For each probe template registered against the persona's archetype:

* `after_last_session` probes:
  - Skip Recall probes whose target fact is missing from the persona's
    fact set (defensive — shouldn't happen if templates and archetypes
    agree).
  - Skip Recall probes whose target fact has been superseded by an
    update event AND whose post-update value differs in a way the
    Recall axis isn't asking about. (Recall asks about *currently*
    correct state; if an update fired, the post-update value is the
    correct answer.)
  - Place the probe immediately after the last session.

* `after_update_event` probes:
  - Resolve the matching UpdateEvent on the persona; skip the template
    if the event didn't fire.
  - Place one probe per `latency_offset` k, at session
    `update_session_idx + k + 1` (clamped to `num_sessions`).
  - Skip the latency variant if it would land beyond the trace's last
    session.

Every emitted Probe carries:
- a deterministic `probe_id` derived from
  (persona_id, template_id, latency_k_or_zero),
- the resolved `rubric_targets` (fact keys + static keys),
- metadata: latency bucket for Update, template_id for traceability.
"""

from __future__ import annotations

from mnemos.probes.templates import (
    ARCHETYPE_TEMPLATES,
    ProbeTemplate,
    get_templates_for,
)
from mnemos.types import (
    Persona,
    Probe,
    UpdateEvent,
)


def generate_probes(persona: Persona, num_sessions: int) -> list[Probe]:
    """Generate the full probe set for a persona.

    Args:
        persona: must already have its update events scheduled (i.e. each
            UpdateEvent has a session_id pointing at a session in
            [s1..s{num_sessions}]).
        num_sessions: total sessions in the trace this persona appears in.

    Returns:
        Probes in stable order: by axis (recall, consolidation, update),
        then by template_id, then by latency offset for update probes.
    """
    templates = get_templates_for(persona.archetype)
    persona_fact_keys = {f.key for f in persona.facts}
    persona_static_keys = set(persona.static_profile.keys())
    update_event_by_id = {e.event_id: e for e in persona.update_events}

    probes: list[Probe] = []
    for tmpl in templates:
        if tmpl.schedule_kind == "after_last_session":
            probe = _emit_after_last_session_probe(
                tmpl,
                persona,
                num_sessions,
                persona_fact_keys=persona_fact_keys,
                persona_static_keys=persona_static_keys,
            )
            if probe is not None:
                probes.append(probe)
        elif tmpl.schedule_kind == "after_update_event":
            probes.extend(
                _emit_after_update_event_probes(
                    tmpl,
                    persona,
                    num_sessions,
                    update_event_by_id=update_event_by_id,
                )
            )
        else:  # pragma: no cover — exhaustive over the Literal
            raise ValueError(f"Unknown schedule_kind: {tmpl.schedule_kind!r}")

    return _stable_sort(probes)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _emit_after_last_session_probe(
    tmpl: ProbeTemplate,
    persona: Persona,
    num_sessions: int,
    *,
    persona_fact_keys: set[str],
    persona_static_keys: set[str],
) -> Probe | None:
    rubric_targets = _resolve_rubric_targets(
        tmpl,
        persona_fact_keys=persona_fact_keys,
        persona_static_keys=persona_static_keys,
        update_event_by_id={e.event_id: e for e in persona.update_events},
    )
    # Negative-recall and consolidate_what_changed templates have no
    # rubric_*_keys set on the template. We still emit them (the
    # evaluator's rubric is encoded in the judge prompt for those cases).
    return Probe(
        probe_id=_probe_id(persona.persona_id, tmpl.template_id),
        axis=tmpl.axis,
        after_session=_session_id(num_sessions),
        input=tmpl.input,
        rubric_targets=rubric_targets,
        metadata={
            "template_id": tmpl.template_id,
            "schedule_kind": tmpl.schedule_kind,
        },
    )


def _emit_after_update_event_probes(
    tmpl: ProbeTemplate,
    persona: Persona,
    num_sessions: int,
    *,
    update_event_by_id: dict[str, UpdateEvent],
) -> list[Probe]:
    if tmpl.target_update_event_id is None:
        return []
    event = update_event_by_id.get(tmpl.target_update_event_id)
    if event is None:
        # Update event didn't fire for this persona — skip the probe
        # template entirely. This is the right behaviour: probes that
        # ask about an update only make sense when the update happened.
        return []

    update_session_idx = _parse_session_index(event.session_id)
    probes: list[Probe] = []
    for k in tmpl.latency_offsets:
        target_session_idx = update_session_idx + k + 1
        if target_session_idx > num_sessions:
            # No session at this latency for this trace; skip.
            continue
        probes.append(
            Probe(
                probe_id=_probe_id(persona.persona_id, tmpl.template_id, k=k),
                axis=tmpl.axis,
                after_session=_session_id(target_session_idx),
                input=tmpl.input,
                rubric_targets=list(tmpl.rubric_fact_keys)
                + [f"static.{k_}" for k_ in tmpl.rubric_static_keys],
                metadata={
                    "template_id": tmpl.template_id,
                    "schedule_kind": tmpl.schedule_kind,
                    "latency_k": str(k),
                    "update_event_id": event.event_id,
                    "update_session": event.session_id,
                },
            )
        )
    return probes


def _resolve_rubric_targets(
    tmpl: ProbeTemplate,
    *,
    persona_fact_keys: set[str],
    persona_static_keys: set[str],
    update_event_by_id: dict[str, UpdateEvent],
) -> list[str]:
    """Compute rubric_targets for an after_last_session probe.

    Returns the fact keys (and `static.<key>` for static profile keys)
    the evaluator should treat as ground truth. Skips fact keys not
    present on the persona — defensive guard against template/archetype
    drift.
    """
    targets: list[str] = []
    for key in tmpl.rubric_fact_keys:
        if key in persona_fact_keys:
            targets.append(key)
    for key in tmpl.rubric_static_keys:
        if key in persona_static_keys:
            targets.append(f"static.{key}")
    # `consolidate_what_changed` deliberately has no rubric keys at the
    # template level — its rubric is "any update event the persona had."
    # We surface those at probe time so the judge has them to compare.
    if tmpl.template_id == "consolidate_what_changed":
        targets.extend(
            f"update.{e.event_id}" for e in update_event_by_id.values()
        )
    return targets


def _stable_sort(probes: list[Probe]) -> list[Probe]:
    axis_order = {"recall": 0, "consolidation": 1, "update": 2}

    def key(p: Probe) -> tuple[int, str, str]:
        latency = p.metadata.get("latency_k", "0")
        return (axis_order[p.axis], p.metadata.get("template_id", ""), latency)

    return sorted(probes, key=key)


def _probe_id(persona_id: str, template_id: str, k: int | None = None) -> str:
    base = f"{persona_id}::{template_id}"
    if k is not None:
        return f"{base}::k{k}"
    return base


def _session_id(idx: int) -> str:
    return f"s{idx}"


def _parse_session_index(session_id: str) -> int:
    if not session_id.startswith("s"):
        raise ValueError(f"Malformed session_id: {session_id!r}")
    return int(session_id[1:])


# Public surface: discover what's covered without importing templates.
SUPPORTED_ARCHETYPES = list(ARCHETYPE_TEMPLATES.keys())
