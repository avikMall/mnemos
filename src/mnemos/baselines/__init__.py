"""Reference memory architectures.

A baseline implements the MemorySystem protocol from `mnemos.protocol`:
two methods, `ingest(session)` and `respond(probe, current_session_context)`.
That's the entire surface area; everything else is internal to the baseline.

See SPEC.md §6.
"""
