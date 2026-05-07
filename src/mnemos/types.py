"""Core data types for Mnemos.

These mirror the schemas described in SPEC.md §4 and §5. Pydantic models
provide validation, JSON (de)serialization, and a single source of truth
for what a persona, trace, and probe look like across the codebase.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Personas
# ---------------------------------------------------------------------------


class Archetype(str, Enum):
    """Persona archetypes shipping with v1.

    Skewed Boardy-adjacent (the people Boardy tends to talk to) but the
    framework is general. Add archetypes by extending this enum and adding
    a template under personas/templates/.
    """

    EARLY_STAGE_FOUNDER = "early_stage_founder"
    MID_CAREER_OPERATOR = "mid_career_operator"
    RESEARCHER_SEEKING_COLLABORATORS = "researcher_seeking_collaborators"
    JOB_SEEKER_IN_SLUMP = "job_seeker_in_slump"
    RECENTLY_FUNDED_FOUNDER = "recently_funded_founder"


class Fact(BaseModel):
    """A single fact about the persona, with provenance for the evaluator."""

    key: str  # stable identifier, e.g. "co_founder_name"
    value: str
    introduced_session: str | None = None  # set when scheduled into a trace
    superseded_by: str | None = None  # key of a later fact that replaces this


class UpdateEvent(BaseModel):
    """A scheduled change in persona state between sessions."""

    event_id: str
    session_id: str  # the session in which the update is communicated
    description: str  # natural-language description used by the simulator
    fact_changes: list[Fact] = Field(default_factory=list)


class Persona(BaseModel):
    """A synthetic user across the lifespan of a benchmark run.

    See SPEC.md §4. Held-out truth annotations live here and are NEVER
    shown to the agent under test — the evaluator uses them to score.
    """

    persona_id: str
    archetype: Archetype
    static_profile: dict[str, str]  # name, occupation, location, etc.
    facts: list[Fact]  # the full ground-truth fact set
    update_events: list[UpdateEvent] = Field(default_factory=list)
    seed: int


# ---------------------------------------------------------------------------
# Conversation traces
# ---------------------------------------------------------------------------


Role = Literal["user", "agent"]


class Turn(BaseModel):
    role: Role
    text: str


class Session(BaseModel):
    session_id: str
    timestamp: datetime
    turns: list[Turn]
    scheduled_disclosures: list[str] = Field(default_factory=list)  # fact keys
    scheduled_updates: list[str] = Field(default_factory=list)  # event ids


# ---------------------------------------------------------------------------
# Probes
# ---------------------------------------------------------------------------


Axis = Literal["recall", "consolidation", "update"]


class Probe(BaseModel):
    """A single evaluation question posed after a specific session.

    `rubric_targets` are fact keys (or persona-truth annotation keys) the
    evaluator will use as ground truth when scoring the agent's response.
    They are NEVER shown to the agent.
    """

    probe_id: str
    axis: Axis
    after_session: str
    input: str  # the user-side text given to the agent at probe time
    rubric_targets: list[str]
    metadata: dict[str, str] = Field(default_factory=dict)  # e.g. latency bucket


# ---------------------------------------------------------------------------
# Traces
# ---------------------------------------------------------------------------


class Trace(BaseModel):
    """A full multi-session interaction for one persona, plus probes."""

    trace_id: str
    persona_id: str
    generator_version: str
    seed: int
    sessions: list[Session]
    probes: list[Probe]


# ---------------------------------------------------------------------------
# Memory system interface (see SPEC.md §6)
# ---------------------------------------------------------------------------


class ProbeResponse(BaseModel):
    """What a memory system returns when asked a probe."""

    text: str
    retrieved_context: list[str] = Field(default_factory=list)  # for inspection
    metadata: dict[str, str] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


Score = Literal[-1, 0, 1, 2]


class ProbeScore(BaseModel):
    probe_id: str
    score: Score
    justification: str
    judge_model: str
    judge_run_index: int  # 0..N for variance reporting


class TraceResults(BaseModel):
    trace_id: str
    baseline_name: str
    git_sha: str
    agent_model: str
    judge_model: str
    trace_set_version: str
    probe_scores: list[ProbeScore]
