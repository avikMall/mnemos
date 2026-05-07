"""Thin LLM client interface used by the trace generator.

We define a small `LLMClient` protocol and ship two implementations:
- `AnthropicLLMClient` — wraps the Anthropic SDK. Real API calls.
- `DeterministicMockLLMClient` — returns canned, hash-driven responses.
  Used in unit tests so the orchestration is testable without keys.

Both clients honour a simple chat-completions style:
    client.chat(system=..., messages=[{role, content}, ...]) -> str

Why the indirection? Two reasons:
1. We want the trace generator to be cleanly testable without spending
   real money or tying tests to network availability.
2. As Mnemos grows, swapping in alternative model families (for the
   second-judge cross-validation noted in SPEC §10) becomes a one-line
   change.

Caching (planned)
-----------------

A v1.x improvement is a content-addressed cache that hashes (model,
system, messages) → response and persists to disk. This makes traces
effectively deterministic after first generation and dramatically
cheaper to re-run during evaluator development. Not implemented yet
to keep this commit focused; the interface below is shaped for it
(see `LLMClient.chat` returning a plain str — easy to wrap).
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from typing import Protocol


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------


class LLMClient(Protocol):
    """Minimal chat-completions interface."""

    model: str

    def chat(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 600,
        temperature: float = 0.0,
    ) -> str: ...


# ---------------------------------------------------------------------------
# Anthropic client
# ---------------------------------------------------------------------------


@dataclass
class AnthropicLLMClient:
    """Real Anthropic-API client.

    Imports the SDK lazily so unit tests don't pay the import cost or
    require the package to be installed. The API key is read from the
    environment (`ANTHROPIC_API_KEY`).
    """

    model: str = "claude-sonnet-4-6"

    def chat(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 600,
        temperature: float = 0.0,
    ) -> str:
        import anthropic  # local import: keep test paths SDK-free

        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        resp = client.messages.create(
            model=self.model,
            system=system,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        # The SDK returns a list of content blocks; we want the text.
        return "".join(
            block.text for block in resp.content if hasattr(block, "text")
        )


# ---------------------------------------------------------------------------
# Mock client (for tests)
# ---------------------------------------------------------------------------


@dataclass
class DeterministicMockLLMClient:
    """Returns canned responses derived from the input.

    The response is a short string of the form:
        "<role-tag>:<digest>"
    where `role-tag` is "user_sim" or "agent" depending on the system
    prompt's first line, and `digest` is the first 8 chars of a SHA-256
    over (system, messages, model). This gives:
      - Determinism: identical input → identical output.
      - Distinguishability: different input → different output.
      - No real LLM calls.

    The orchestrator's session loop has a turn budget and an
    end-session detector, so the mock occasionally emits an
    end-session token to exercise the early-stop path. It does this
    based on a deterministic function of the input length.
    """

    model: str = "mock-deterministic-v1"
    end_session_token: str = "[END_SESSION]"
    # Number of "user turns" before the mock simulator emits the
    # end-session token. Settable for tests.
    end_after_user_turns: int = 4

    def chat(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 600,
        temperature: float = 0.0,
    ) -> str:
        role_tag = self._infer_role(system)
        digest = self._digest(system, messages)
        # If we're playing the user simulator and we've issued enough
        # user turns, signal end of session.
        if role_tag == "user_sim":
            user_turns = sum(1 for m in messages if m.get("role") == "assistant")
            # NOTE: in our orchestrator the user simulator's outputs are
            # passed back as `assistant` from its own perspective, so
            # `assistant` count = number of user-sim turns we've already
            # produced. That's what we count here.
            if user_turns >= self.end_after_user_turns:
                return f"user_sim:{digest} {self.end_session_token}"
            return f"user_sim:{digest}"
        return f"agent:{digest}"

    @staticmethod
    def _infer_role(system: str) -> str:
        first_line = system.strip().splitlines()[0].lower()
        if "simulating" in first_line or "user" in first_line and "playing" not in first_line:
            return "user_sim"
        # Heuristic: any system prompt starting with "you are simulating ..."
        # is the simulator. Everything else is the agent.
        if first_line.startswith("you are simulating"):
            return "user_sim"
        return "agent"

    @staticmethod
    def _digest(system: str, messages: list[dict]) -> str:
        payload = json.dumps(
            {"system": system, "messages": messages}, sort_keys=True
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:8]
