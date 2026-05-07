"""Probe templates and generation.

A probe is a single evaluation question posed after a specific session
(see SPEC.md §3 and §5). v1 covers three axes — Recall, Consolidation,
Update — each with its own template family and scheduling rules.

Probes are generated deterministically from a Persona. The generator
makes no LLM calls; the only nondeterminism in the v1 data layer is
trace generation itself.
"""

GENERATOR_VERSION = "v1"
