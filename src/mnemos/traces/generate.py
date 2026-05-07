"""Trace generation orchestration.

Given a Persona, generate a multi-session conversation trace by
running a user-simulator LLM and a stand-in-agent LLM in alternation.
The orchestration logic is deterministic; the only nondeterminism is
the LLM calls themselves (mitigated with temperature=0 and a content
cache in a future commit).

Session loop
------------

For each session 1..num_sessions:
1. Build the user-simulator system prompt from persona + plan.
2. Build a fresh agent system prompt (the stand-in agent has no
   memory across sessions by design — see SPEC §6).
3. Alternate turns:
   user_sim turn → agent turn → user_sim turn → ...
4. Stop when:
   - The user-sim emits the end-session token, OR
   - The turn budget (max_user_turns_per_session) is hit.

Notes
-----

- Probes are NOT generated here. They come from `mnemos.probes.generate`
  and are attached to the trace at the end. This keeps the eval
  surface independent of what the trace looks like.
- We record the resolved fact values *as of each session* so the
  evaluator can later verify the simulator behaved correctly. (This
  also gives us a cheap downstream sanity check: if the simulator
  said "I left my job" when no update was scheduled, that's a bug to
  fix in the prompt.)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from mnemos.probes.generate import generate_probes
from mnemos.traces import GENERATOR_VERSION
from mnemos.traces.disclosure import (
    all_disclosed_keys_through,
    build_disclosure_plan,
)
from mnemos.traces.llm import LLMClient
from mnemos.traces.prompts import (
    END_SESSION_TOKEN,
    PROMPTS_VERSION,
    STAND_IN_AGENT_SYSTEM,
    render_user_simulator_system,
)
from mnemos.types import (
    Persona,
    Session,
    Trace,
    Turn,
    UpdateEvent,
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@dataclass
class TraceGenConfig:
    """Knobs for trace generation. v1 defaults are conservative."""

    num_sessions: int = 6
    # Per-session caps. The orchestrator stops at whichever comes first:
    # the simulator emitting an end-session token, or the turn budget.
    max_user_turns_per_session: int = 12
    min_user_turns_per_session: int = 4
    # Turn-level token budget for the LLM calls.
    max_tokens_per_turn: int = 400
    # Temperature for both simulator and agent. v1 defaults to 0 for
    # near-deterministic output.
    temperature: float = 0.0
    # Wall-clock spacing between sessions (just for trace metadata).
    session_spacing_days: int = 7


def generate_trace(
    persona: Persona,
    *,
    config: TraceGenConfig | None = None,
    user_sim_client: LLMClient,
    agent_client: LLMClient,
    seed: int | None = None,
    base_timestamp: datetime | None = None,
) -> Trace:
    """Generate a Trace for one persona.

    Args:
        persona: the persona to simulate.
        config: generation knobs; defaults applied if None.
        user_sim_client: LLM client for the user-simulator role.
        agent_client: LLM client for the stand-in agent role. May be
            the same instance as `user_sim_client`; we keep them as
            separate parameters so callers can use different models or
            mock combinations during development.
        seed: optional integer seed. Recorded in trace metadata. (The
            persona already has its own seed; this lets you re-trace a
            single persona under different conditions.)
        base_timestamp: timestamp for session 1; later sessions are
            spaced `session_spacing_days` apart. Defaults to now (UTC).

    Returns:
        A `Trace` object with sessions, probes, and metadata recorded.
    """
    cfg = config or TraceGenConfig()
    if base_timestamp is None:
        base_timestamp = datetime.now(timezone.utc)

    plan = build_disclosure_plan(persona, num_sessions=cfg.num_sessions)
    updates_by_session = _index_updates_by_session(persona.update_events)

    sessions: list[Session] = []
    for idx in range(1, cfg.num_sessions + 1):
        session = _generate_session(
            persona=persona,
            session_idx=idx,
            num_sessions=cfg.num_sessions,
            disclosure_plan=plan,
            updates_this_session=updates_by_session.get(f"s{idx}", []),
            timestamp=base_timestamp + timedelta(days=cfg.session_spacing_days * (idx - 1)),
            user_sim_client=user_sim_client,
            agent_client=agent_client,
            cfg=cfg,
        )
        sessions.append(session)

    probes = generate_probes(persona, num_sessions=cfg.num_sessions)

    trace_id = f"trace__{persona.persona_id}"
    if seed is not None:
        trace_id = f"{trace_id}__seed_{seed}"

    return Trace(
        trace_id=trace_id,
        persona_id=persona.persona_id,
        generator_version=GENERATOR_VERSION,
        seed=seed if seed is not None else persona.seed,
        sessions=sessions,
        probes=probes,
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


@dataclass
class _SessionRunState:
    """Mutable state inside a single session's loop."""

    turns: list[Turn] = field(default_factory=list)
    user_turn_count: int = 0
    agent_turn_count: int = 0
    end_signaled: bool = False


def _generate_session(
    *,
    persona: Persona,
    session_idx: int,
    num_sessions: int,
    disclosure_plan: list[list[str]],
    updates_this_session: list[UpdateEvent],
    timestamp: datetime,
    user_sim_client: LLMClient,
    agent_client: LLMClient,
    cfg: TraceGenConfig,
) -> Session:
    user_sim_system = render_user_simulator_system(
        name=persona.static_profile.get("name", "the user"),
        occupation=persona.static_profile.get("occupation", "(unspecified)"),
        location=persona.static_profile.get("location", "(unspecified)"),
        persona_facts_block=_format_facts_block(persona),
        prior_disclosures_block=_format_prior_disclosures(
            persona, disclosure_plan, session_idx
        ),
        session_idx=session_idx,
        num_sessions=num_sessions,
        new_disclosures_block=_format_new_disclosures(
            persona, disclosure_plan[session_idx - 1]
        ),
        updates_block=_format_updates(updates_this_session),
    )

    state = _SessionRunState()

    # The conversation history we maintain is from the *user simulator's*
    # perspective. Its OWN turns appear with role="assistant" in its
    # message list. The agent we call separately sees a transposed view.
    user_sim_history: list[dict] = []
    agent_history: list[dict] = []

    while not state.end_signaled and state.user_turn_count < cfg.max_user_turns_per_session:
        # User-sim turn
        user_text = user_sim_client.chat(
            system=user_sim_system,
            messages=user_sim_history,
            max_tokens=cfg.max_tokens_per_turn,
            temperature=cfg.temperature,
        )
        clean_user_text, ended = _strip_end_token(user_text)
        state.turns.append(Turn(role="user", text=clean_user_text))
        user_sim_history.append({"role": "assistant", "content": user_text})
        agent_history.append({"role": "user", "content": clean_user_text})
        state.user_turn_count += 1
        if ended and state.user_turn_count >= cfg.min_user_turns_per_session:
            state.end_signaled = True
            break
        # If the simulator tries to end too early, ignore the token and
        # continue. The minimum-turn floor protects against pathological
        # one-turn sessions when the LLM gets confused.

        # Agent turn
        agent_text = agent_client.chat(
            system=STAND_IN_AGENT_SYSTEM,
            messages=agent_history,
            max_tokens=cfg.max_tokens_per_turn,
            temperature=cfg.temperature,
        )
        state.turns.append(Turn(role="agent", text=agent_text))
        agent_history.append({"role": "assistant", "content": agent_text})
        user_sim_history.append({"role": "user", "content": agent_text})
        state.agent_turn_count += 1

    return Session(
        session_id=f"s{session_idx}",
        timestamp=timestamp,
        turns=state.turns,
        scheduled_disclosures=list(disclosure_plan[session_idx - 1]),
        scheduled_updates=[e.event_id for e in updates_this_session],
    )


def _index_updates_by_session(
    events: list[UpdateEvent],
) -> dict[str, list[UpdateEvent]]:
    out: dict[str, list[UpdateEvent]] = {}
    for e in events:
        out.setdefault(e.session_id, []).append(e)
    return out


def _strip_end_token(text: str) -> tuple[str, bool]:
    if END_SESSION_TOKEN in text:
        return text.replace(END_SESSION_TOKEN, "").strip(), True
    return text, False


# ---------------------------------------------------------------------------
# Prompt-block formatters
# ---------------------------------------------------------------------------


def _format_facts_block(persona: Persona) -> str:
    """Multi-line block describing all persona facts.

    These are facts the simulator KNOWS about itself, even if it
    hasn't disclosed them yet. We put them all in the system prompt
    because the simulator needs the full picture to react authentically
    when the agent asks open questions.
    """
    lines = []
    for f in persona.facts:
        lines.append(f"- {f.key}: {f.value}")
    return "\n".join(lines) if lines else "(none)"


def _format_prior_disclosures(
    persona: Persona,
    plan: list[list[str]],
    session_idx: int,
) -> str:
    """What the simulator has 'said' in earlier sessions, by fact key."""
    keys = all_disclosed_keys_through(plan, session_idx - 1)
    if not keys:
        return "(none — this is the first session.)"
    lines = []
    for f in persona.facts:
        if f.key in keys:
            lines.append(f"- {f.key}: {f.value}")
    return "\n".join(lines) if lines else "(none.)"


def _format_new_disclosures(persona: Persona, keys: list[str]) -> str:
    if not keys:
        return "  (none scheduled — focus on follow-ups, deeper exploration, or the updates below.)"
    lines = []
    for f in persona.facts:
        if f.key in keys:
            lines.append(f"  - {f.key}: {f.value}")
    return "\n".join(lines) if lines else "  (none.)"


def _format_updates(updates: list[UpdateEvent]) -> str:
    if not updates:
        return "  (none in this session.)"
    lines = []
    for e in updates:
        lines.append(f"  - [{e.event_id}] {e.description}")
    return "\n".join(lines)
