"""The MemorySystem protocol that every baseline implements.

This is the only contract baselines must satisfy. Keep this file tiny on
purpose: a small, stable surface is what makes Mnemos open to many memory
architectures, including ones we haven't thought of yet.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from mnemos.types import ProbeResponse, Probe, Session


@runtime_checkable
class MemorySystem(Protocol):
    """A memory system under test.

    `ingest` is called once per session, in order, before the next session
    begins. The system may store or transform the session however it likes.

    `respond` is called once per probe, after the corresponding session has
    been ingested. The system must produce a textual response; retrieved
    context is reported for inspection but does not affect scoring.
    """

    name: str

    def ingest(self, session: Session) -> None: ...

    def respond(self, probe: Probe, current_session_context: str) -> ProbeResponse: ...
