"""Probe templates organized by axis.

Design choices
--------------

We keep probe templates fully declarative — no callables, no closures —
so they round-trip through JSON cleanly and so it's obvious to a reader
what's in the benchmark just by reading this file.

A probe template names:
- the axis it tests,
- the input string the simulated user will send to the agent,
- the rubric-target fact keys the evaluator will use as ground truth,
- and a `schedule_kind` describing when the probe fires.

For Update probes, rubric targets reference the *post-update* value at
probe time. The probe generator (probes/generate.py) resolves this by
walking the persona's `update_events` and `facts` in order — the agent
under test is then judged on whether it can do the same kind of
reasoning over the conversation history.

Negative-recall probes
----------------------

We include a small pool of "things that were never disclosed in the
trace" as negative-recall probes. A good memory system says it doesn't
know rather than confabulating. Per SPEC §3.1, confabulation gets the
hardest negative score (-1).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from mnemos.types import Archetype, Axis


ScheduleKind = Literal[
    "after_last_session",  # fired once, after the final session of the trace
    "after_update_event",  # fired k sessions after a specific update event
]


@dataclass(frozen=True)
class ProbeTemplate:
    """A reusable probe spec.

    `rubric_fact_keys` and `rubric_static_keys` reference Persona.facts
    and Persona.static_profile respectively. The probe generator
    instantiates the probe by filling rubric_targets with the keys
    relevant to the specific persona instance.

    `target_update_event_id` is only meaningful when
    `schedule_kind == "after_update_event"`. It identifies which
    UpdateSpec the probe pairs with.
    """

    template_id: str
    axis: Axis
    input: str
    schedule_kind: ScheduleKind
    rubric_fact_keys: tuple[str, ...] = ()
    rubric_static_keys: tuple[str, ...] = ()
    target_update_event_id: str | None = None
    # For after_update_event probes: probe at k=offsets sessions after.
    # k=0 means the next session after the update; k=2 means three after.
    latency_offsets: tuple[int, ...] = (0,)
    # Free-form notes for human readers; ignored by the generator.
    notes: str = ""


# ---------------------------------------------------------------------------
# Recall probes (SPEC §3.1)
# ---------------------------------------------------------------------------

# Direct-ask templates: each pairs an input phrasing with the fact key it
# probes. We keep the phrasings conversational rather than survey-like so
# they look natural inside a generated trace.
RECALL_DIRECT: tuple[ProbeTemplate, ...] = (
    ProbeTemplate(
        template_id="recall_cofounder_direct",
        axis="recall",
        input="Quick refresher — who's my co-founder again? I want to make sure you have it right.",
        schedule_kind="after_last_session",
        rubric_fact_keys=("co_founder_name",),
    ),
    ProbeTemplate(
        template_id="recall_project_direct",
        axis="recall",
        input="Can you remind me how I described what we're building, in your own words?",
        schedule_kind="after_last_session",
        rubric_fact_keys=("current_project",),
    ),
    ProbeTemplate(
        template_id="recall_fundraising_direct",
        axis="recall",
        input="Where did I say I am with fundraising right now?",
        schedule_kind="after_last_session",
        rubric_fact_keys=("fundraising_stage",),
    ),
    ProbeTemplate(
        template_id="recall_hiring_direct",
        axis="recall",
        input="What's the role I told you I'm prioritizing on the hiring side?",
        schedule_kind="after_last_session",
        rubric_fact_keys=("hiring_priority",),
    ),
    ProbeTemplate(
        template_id="recall_location_direct",
        axis="recall",
        input="Where am I based, again? I think I mentioned it on our first call.",
        schedule_kind="after_last_session",
        rubric_static_keys=("location",),
    ),
)

# Indirect-dependency templates: the user references something obliquely
# and a coherent agent reply requires retrieving the underlying fact.
RECALL_INDIRECT: tuple[ProbeTemplate, ...] = (
    ProbeTemplate(
        template_id="recall_cofounder_indirect",
        axis="recall",
        input=(
            "I had another one of those tough conversations with my co-founder "
            "last night. Same dynamic as before. Curious what you'd reflect back."
        ),
        schedule_kind="after_last_session",
        rubric_fact_keys=("co_founder_name",),
        notes=(
            "Coherent reply should reference the co-founder by name OR explicitly "
            "ask for it. A reply that ignores prior context fails recall."
        ),
    ),
)

# Negative-recall templates: probe topics the persona archetype never
# discloses. Expected behaviour: the agent declines to invent a memory.
RECALL_NEGATIVE: tuple[ProbeTemplate, ...] = (
    ProbeTemplate(
        template_id="recall_negative_pet",
        axis="recall",
        input="What did I end up telling you about my pet — was it the dog or the cat one?",
        schedule_kind="after_last_session",
        notes=(
            "No pet was ever disclosed. Correct behaviour: the agent says it "
            "doesn't recall any mention of a pet. Fabricating one scores -1."
        ),
    ),
    ProbeTemplate(
        template_id="recall_negative_sibling",
        axis="recall",
        input="Remind me what I shared about my sister last time we talked.",
        schedule_kind="after_last_session",
        notes=(
            "No sister was ever disclosed. Same scoring as recall_negative_pet."
        ),
    ),
)

RECALL_TEMPLATES: tuple[ProbeTemplate, ...] = (
    RECALL_DIRECT + RECALL_INDIRECT + RECALL_NEGATIVE
)


# ---------------------------------------------------------------------------
# Consolidation probes (SPEC §3.2)
# ---------------------------------------------------------------------------

# Open-ended questions whose good answer requires synthesizing across
# sessions, not just retrieving a single fact.
CONSOLIDATION_TEMPLATES: tuple[ProbeTemplate, ...] = (
    ProbeTemplate(
        template_id="consolidate_whats_on_mind",
        axis="consolidation",
        input=(
            "Stepping back across our conversations so far — what would you "
            "say is most on my mind right now?"
        ),
        schedule_kind="after_last_session",
        rubric_fact_keys=(
            "emotional_undercurrent",
            "fundraising_stage",
            "hiring_priority",
        ),
        notes=(
            "Good answer surfaces the latent emotional theme AND grounds it in "
            "specific topics (fundraising, hiring). Answer that just lists "
            "facts without synthesis scores 0."
        ),
    ),
    ProbeTemplate(
        template_id="consolidate_who_am_i_professionally",
        axis="consolidation",
        input=(
            "If you had to describe who I am professionally based only on what "
            "I've shared in our conversations, what would you say? I'm curious "
            "how it's landing."
        ),
        schedule_kind="after_last_session",
        rubric_fact_keys=("current_project", "fundraising_stage"),
        rubric_static_keys=("occupation",),
    ),
    ProbeTemplate(
        template_id="consolidate_what_changed",
        axis="consolidation",
        input=(
            "Looking back at how this has evolved over the past few times "
            "we've talked, what's actually shifted?"
        ),
        schedule_kind="after_last_session",
        rubric_fact_keys=(),  # filled at gen time from update_events
        notes=(
            "Good answer surfaces real shifts (driven by update_events). "
            "Answers that say 'nothing has changed' when an update fired score -1."
        ),
    ),
)


# ---------------------------------------------------------------------------
# Update probes (SPEC §3.3)
# ---------------------------------------------------------------------------

# These pair with archetype update events (see personas/templates.py).
# `target_update_event_id` MUST match an UpdateSpec.event_id; the probe
# generator skips probes whose paired event didn't actually fire for a
# given persona.
#
# `latency_offsets` controls the latency-binning for the Update axis:
# - k=0: probe in the session immediately after the update.
# - k=1: probe two sessions after.
# - k=2: probe three sessions after (often the last session).
# Probes whose target session would exceed num_sessions are skipped.

UPDATE_TEMPLATES: tuple[ProbeTemplate, ...] = (
    ProbeTemplate(
        template_id="update_cofounder_status",
        axis="update",
        input="Catch me up — where are things with my co-founder?",
        schedule_kind="after_update_event",
        rubric_fact_keys=("co_founder_name",),
        target_update_event_id="cofounder_departs",
        latency_offsets=(0, 1, 2),
        notes=(
            "Post-update truth: 'co-founder departed'. Replies that still treat "
            "them as present score 0; mixed/confused replies score -1; correct "
            "post-update reasoning scores 2 (with explicit acknowledgment) or "
            "1 (post-update without acknowledgment)."
        ),
    ),
    ProbeTemplate(
        template_id="update_fundraising_status",
        axis="update",
        input="How's fundraising going?",
        schedule_kind="after_update_event",
        rubric_fact_keys=("fundraising_stage",),
        target_update_event_id="round_closes",
        latency_offsets=(0, 1, 2),
    ),
    ProbeTemplate(
        template_id="update_what_youre_building",
        axis="update",
        input="Quick gut check — what are you building right now? Want to make sure I have the latest framing.",
        schedule_kind="after_update_event",
        rubric_fact_keys=("current_project",),
        target_update_event_id="pivot_announced",
        latency_offsets=(0, 1, 2),
    ),
)


# ---------------------------------------------------------------------------
# Archetype → template registry
# ---------------------------------------------------------------------------

# v1 ships the same template family for every archetype that has the
# matching fact keys. As we add archetypes that DON'T have, say,
# `fundraising_stage`, we'll narrow the template lists per-archetype.

ARCHETYPE_TEMPLATES: dict[Archetype, tuple[ProbeTemplate, ...]] = {
    Archetype.EARLY_STAGE_FOUNDER: (
        RECALL_TEMPLATES + CONSOLIDATION_TEMPLATES + UPDATE_TEMPLATES
    ),
}


def get_templates_for(archetype: Archetype) -> tuple[ProbeTemplate, ...]:
    if archetype not in ARCHETYPE_TEMPLATES:
        raise NotImplementedError(
            f"Probe templates not yet defined for archetype {archetype.value!r}. "
            f"v1 ships with: {[a.value for a in ARCHETYPE_TEMPLATES]}."
        )
    return ARCHETYPE_TEMPLATES[archetype]
