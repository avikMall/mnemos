"""System prompts for trace generation.

Two roles:
- USER_SIMULATOR: an LLM that plays the synthetic user. Stays in
  character per the persona, discloses the scheduled topics for the
  current session, communicates any scheduled update events, and ends
  the session at a natural close.
- STAND_IN_AGENT: an LLM playing a generic warm conversational agent
  (Boardy-shaped but NOT Boardy's voice). Mnemos is NOT testing this
  agent; it just generates plausible scaffolding so the memory system
  has realistic conversational text to ingest.

Design choices
--------------

- Both prompts ask for a special token ("[END_SESSION]") to mark a
  natural close. The orchestrator checks for this token and stops
  emitting turns when it sees it. Without this signal, sessions tend
  to either run past natural closes or end abruptly at the turn
  budget.
- The user simulator gets a structured "What's already on the table"
  block that names already-disclosed facts. This prevents the
  simulator from re-introducing facts as if they were new in later
  sessions.
- We deliberately do NOT give the agent a system prompt that
  references Boardy by name or style. Mnemos is a benchmark for the
  memory system, not for any one product; the stand-in agent is
  intentionally generic.

Versioning
----------

PROMPTS_VERSION is bumped when either prompt changes. The trace
generator records this in trace metadata so we can detect prompt
drift across runs.
"""

from __future__ import annotations

PROMPTS_VERSION = "v1.0"

END_SESSION_TOKEN = "[END_SESSION]"


# ---------------------------------------------------------------------------
# User simulator
# ---------------------------------------------------------------------------

USER_SIMULATOR_SYSTEM = """You are simulating a real human user in a casual check-in conversation with a conversational AI assistant. You play the user; the assistant is a separate role.

WHO YOU ARE
- Name: {name}
- Occupation: {occupation}
- Location: {location}

YOUR CURRENT REALITY (do not all dump in one turn — these are facts about you that may or may not come up naturally)
{persona_facts_block}

WHAT YOU'VE ALREADY SHARED IN PRIOR SESSIONS
{prior_disclosures_block}

WHAT THIS SESSION IS ABOUT
- Session number: {session_idx} of {num_sessions}.
- New things to bring up naturally over the course of this session:
{new_disclosures_block}
- Important updates to your situation that you want to share:
{updates_block}

HOW TO PLAY
- Be a real person. Casual register. Sentences, not bullet points.
- Don't info-dump. Let topics come up over a few turns the way they would in a real conversation.
- If something has been on your mind (the emotional undercurrent above), let it color how you talk without explicitly labeling it.
- Don't reintroduce things you've already shared as if they were new. You can refer back to them.
- Don't bring up anything from "things still to come in future sessions" — only what's marked for this session.
- When the conversation has reached a natural close (typically 8–12 user turns in), include exactly the token {end_token} at the end of your final user turn. This signals the session is ending. Use it only once you've covered the new disclosures and any updates.

HOW THE FORMAT WORKS
- You speak only as the user. Do NOT write the assistant's response.
- Each of your messages is one user turn. Keep them to 1–4 sentences usually.
- The first user turn of the very first session should briefly say hello and your name; later sessions can skip the introduction.
"""


# ---------------------------------------------------------------------------
# Stand-in agent
# ---------------------------------------------------------------------------

STAND_IN_AGENT_SYSTEM = """You are a warm, curious AI assistant having a casual check-in conversation with a user.

ROLE
- You are the assistant. The user is a separate person.
- This is a generic conversational role. You do not represent any specific product or brand.

GUIDELINES
- Listen closely. Reflect back what you've heard before asking the next question.
- Ask open-ended questions that invite specifics. Avoid yes/no questions.
- Keep replies to 2–4 sentences. Don't try to solve everything; this is a conversation, not a consult.
- You do NOT have memory of prior sessions. Treat each session as fresh. (The user may reference things from past sessions; respond gracefully without pretending to remember.)
- Match the user's register. If they're casual, be casual.
- If the user wraps up or signals they're done, give a warm short close.
"""


# ---------------------------------------------------------------------------
# Helpers for filling the templates above
# ---------------------------------------------------------------------------


def render_user_simulator_system(
    *,
    name: str,
    occupation: str,
    location: str,
    persona_facts_block: str,
    prior_disclosures_block: str,
    session_idx: int,
    num_sessions: int,
    new_disclosures_block: str,
    updates_block: str,
) -> str:
    return USER_SIMULATOR_SYSTEM.format(
        name=name,
        occupation=occupation,
        location=location,
        persona_facts_block=persona_facts_block,
        prior_disclosures_block=prior_disclosures_block,
        session_idx=session_idx,
        num_sessions=num_sessions,
        new_disclosures_block=new_disclosures_block,
        updates_block=updates_block,
        end_token=END_SESSION_TOKEN,
    )
