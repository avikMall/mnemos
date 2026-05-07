"""Persona archetype templates.

Each template defines, for a given archetype, the *structure* of personas
generated from it: what fact keys exist, what update events are possible,
and what value pools the generator draws from. Concrete personas are
produced by `personas.generate.generate_persona(archetype, seed)`.

Design notes:
- Personas are deterministic given (archetype, seed). No LLM calls.
- Fact values come from small curated pools — enough variety to avoid
  trivial pattern-matching, narrow enough that we know exactly what's in
  the benchmark.
- Update events are structured: each one names the fact it changes and
  carries a natural-language description used by the trace simulator.
- We deliberately keep these tight and Boardy-adjacent for v1. The
  framework generalizes; we'd rather ship five high-quality archetypes
  than fifty noisy ones.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from mnemos.types import Archetype


@dataclass(frozen=True)
class FactSpec:
    """Specification for a single fact slot in a persona archetype."""

    key: str
    description: str  # what this fact is, for human readers
    value_pool: tuple[str, ...]  # generator picks one


@dataclass(frozen=True)
class UpdateSpec:
    """Specification for an update event slot.

    `target_fact_key` is the fact key whose value flips when this event
    fires. `new_value_pool` is what the new value can be; `description_template`
    is the natural-language description, with {old} and {new} placeholders.
    """

    event_id: str
    target_fact_key: str
    new_value_pool: tuple[str, ...]
    description_template: str
    earliest_session_index: int = 2  # don't fire updates in the first session


@dataclass(frozen=True)
class ArchetypeTemplate:
    archetype: Archetype
    static_profile_pools: dict[str, tuple[str, ...]]
    fact_specs: tuple[FactSpec, ...]
    update_specs: tuple[UpdateSpec, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Archetype: early_stage_founder
# ---------------------------------------------------------------------------

EARLY_STAGE_FOUNDER = ArchetypeTemplate(
    archetype=Archetype.EARLY_STAGE_FOUNDER,
    static_profile_pools={
        "name": (
            "Asha Patel",
            "Marcus Chen",
            "Priya Iyer",
            "Daniel Okafor",
            "Mei Tanaka",
            "Sofia Reyes",
            "Liam O'Brien",
            "Noor Hassan",
        ),
        "occupation": (
            "Founder, stealth dev-tools startup",
            "Co-founder, early-stage AI company",
            "Founder, pre-seed B2B SaaS",
            "Co-founder, seed-stage fintech",
        ),
        "location": (
            "Brooklyn, NY",
            "San Francisco, CA",
            "Austin, TX",
            "Remote (Lisbon)",
            "Toronto, ON",
        ),
    },
    fact_specs=(
        FactSpec(
            key="co_founder_name",
            description="Name of the user's primary co-founder.",
            value_pool=(
                "Marco Lin",
                "Jordan Yamamoto",
                "Rita Banerjee",
                "Theo Anders",
                "Yara Khoury",
            ),
        ),
        FactSpec(
            key="current_project",
            description="One-line description of what the company is building.",
            value_pool=(
                "an LLM-native testing harness for backend services",
                "a vertical AI agent for property management firms",
                "an open-source eval infra for voice agents",
                "a memory layer for long-running customer-support agents",
                "a tool that turns design docs into review-ready PR plans",
            ),
        ),
        FactSpec(
            key="fundraising_stage",
            description="Where the user is in fundraising.",
            value_pool=(
                "starting pre-seed conversations",
                "mid-pre-seed, partway through a target list",
                "closing pre-seed, has lead",
                "between rounds, runway under 9 months",
            ),
        ),
        FactSpec(
            key="hiring_priority",
            description="The single most important hire on the user's mind.",
            value_pool=(
                "a founding ML engineer with retrieval/embeddings depth",
                "a founding designer who can own product surface",
                "a head-of-GTM who has done early-stage B2B before",
                "a second backend engineer to share on-call",
            ),
        ),
        FactSpec(
            key="emotional_undercurrent",
            description="The user's mood/emotional theme across early sessions.",
            value_pool=(
                "guarded optimism, occasional fundraising anxiety",
                "burnout risk, working long hours, self-aware about it",
                "energized after a recent product win",
                "frustrated with a co-founder dynamic but not ready to name it",
            ),
        ),
    ),
    update_specs=(
        UpdateSpec(
            event_id="cofounder_departs",
            target_fact_key="co_founder_name",
            new_value_pool=("(none — co-founder departed)",),
            description_template=(
                "{old} has decided to leave the company. The user is "
                "processing the departure and adjusting plans."
            ),
        ),
        UpdateSpec(
            event_id="round_closes",
            target_fact_key="fundraising_stage",
            new_value_pool=(
                "pre-seed closed, focused on hiring",
                "closed a small bridge, extending into Q3",
            ),
            description_template=(
                "Fundraising stage has changed: {old} → {new}. The user is "
                "shifting attention to execution."
            ),
            earliest_session_index=3,
        ),
        UpdateSpec(
            event_id="pivot_announced",
            target_fact_key="current_project",
            new_value_pool=(
                "a developer-tooling product adjacent to the original idea",
                "a thinner B2B wedge derived from initial customer conversations",
            ),
            description_template=(
                "The user has decided to pivot: was {old}, now {new}. They are "
                "still framing the rationale."
            ),
            earliest_session_index=4,
        ),
    ),
)


# ---------------------------------------------------------------------------
# Archetype registry
# ---------------------------------------------------------------------------

# v1 ships with one fully-specified archetype (early_stage_founder) and
# stubs for the other four. Each remaining archetype gets the same FactSpec
# treatment in subsequent commits; we want the structure visible now even
# where the value pools are still being curated.

ARCHETYPES: dict[Archetype, ArchetypeTemplate] = {
    Archetype.EARLY_STAGE_FOUNDER: EARLY_STAGE_FOUNDER,
}


def get_template(archetype: Archetype) -> ArchetypeTemplate:
    """Return the template for an archetype, or raise if not yet implemented."""
    if archetype not in ARCHETYPES:
        raise NotImplementedError(
            f"Archetype {archetype.value!r} is registered in mnemos.types but "
            f"its template is not yet implemented in personas/templates.py. "
            f"v1 ships with: {[a.value for a in ARCHETYPES]}."
        )
    return ARCHETYPES[archetype]
