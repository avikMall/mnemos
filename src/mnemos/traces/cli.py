"""Command-line entry point for trace generation.

Usage
-----

    # Generate ONE trace for a specific (archetype, seed) pair:
    python -m mnemos.traces.cli \
        --archetype early_stage_founder \
        --seed 2 \
        --num-sessions 6 \
        --output-dir traces/v1

    # Generate the full v1 trace set (all 5 archetypes × 10 seeds = 50 traces):
    python -m mnemos.traces.cli --version v1 --output-dir traces/v1

The output is a directory of JSON files, one per trace, named
`<persona_id>.json`. Each file is a serialized `Trace` object including
sessions, probes, and metadata.

Cost note
---------

The default config (6 sessions × ~12 turns × 2 LLM calls per turn) is
roughly 100–150 LLM calls per trace. For the full v1 trace set
(50 traces) plan on ~5K LLM calls. With a Sonnet-class model and
short turns (~400 tokens out), this is in the low-tens-of-dollars
range. Run a single trace first (`--seed 2`) and inspect it before
committing to the full v1 generation.

Reproducibility
---------------

The CLI passes the persona's own seed as the trace seed by default.
Pin the model with `--model claude-sonnet-4-6` (or whatever you're
running). Trace metadata records both `seed` and `generator_version`;
the agent and judge model versions are recorded later in the
results files.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from mnemos.personas.generate import (
    SUPPORTED_ARCHETYPES,
    generate_persona,
)
from mnemos.traces.generate import TraceGenConfig, generate_trace
from mnemos.traces.llm import AnthropicLLMClient
from mnemos.types import Archetype


# v1 trace set: 5 archetypes × 10 seeds = 50 traces. Right now only
# `early_stage_founder` has a fully-specified template; the rest will
# be added before the public push (see NEXT_STEPS.md).
V1_SEEDS = list(range(100, 110))


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mnemos.traces.cli",
        description="Generate Mnemos conversation traces.",
    )
    p.add_argument(
        "--version",
        help=(
            "Generate a versioned trace set (e.g. 'v1') instead of a "
            "single trace. Mutually exclusive with --archetype/--seed."
        ),
    )
    p.add_argument(
        "--archetype",
        choices=[a.value for a in Archetype],
        help="Archetype for a single-trace run.",
    )
    p.add_argument(
        "--seed",
        type=int,
        help="Persona seed for a single-trace run.",
    )
    p.add_argument(
        "--num-sessions",
        type=int,
        default=6,
        help="Sessions per trace (default: 6).",
    )
    p.add_argument(
        "--max-user-turns",
        type=int,
        default=12,
        help="Max user turns per session (default: 12).",
    )
    p.add_argument(
        "--min-user-turns",
        type=int,
        default=4,
        help="Min user turns per session (default: 4).",
    )
    p.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="LLM temperature for both simulator and agent (default: 0.0).",
    )
    p.add_argument(
        "--model",
        default="claude-sonnet-4-6",
        help="Anthropic model id (default: claude-sonnet-4-6).",
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory to write trace JSON files into. Created if absent.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    if args.version:
        if args.archetype or args.seed is not None:
            print(
                "error: --version is mutually exclusive with --archetype/--seed",
                file=sys.stderr,
            )
            return 2
        return _run_versioned_set(args)

    if not args.archetype or args.seed is None:
        print(
            "error: provide either --version or both --archetype and --seed",
            file=sys.stderr,
        )
        return 2
    return _run_single(args)


def _run_single(args: argparse.Namespace) -> int:
    archetype = Archetype(args.archetype)
    persona = generate_persona(archetype, seed=args.seed)
    cfg = TraceGenConfig(
        num_sessions=args.num_sessions,
        max_user_turns_per_session=args.max_user_turns,
        min_user_turns_per_session=args.min_user_turns,
        temperature=args.temperature,
    )
    client = AnthropicLLMClient(model=args.model)
    trace = generate_trace(
        persona,
        config=cfg,
        user_sim_client=client,
        agent_client=client,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    out = args.output_dir / f"{persona.persona_id}.json"
    out.write_text(trace.model_dump_json(indent=2))
    print(f"wrote {out}")
    return 0


def _run_versioned_set(args: argparse.Namespace) -> int:
    if args.version != "v1":
        print(f"error: unknown version {args.version!r}; expected 'v1'", file=sys.stderr)
        return 2
    cfg = TraceGenConfig(
        num_sessions=args.num_sessions,
        max_user_turns_per_session=args.max_user_turns,
        min_user_turns_per_session=args.min_user_turns,
        temperature=args.temperature,
    )
    client = AnthropicLLMClient(model=args.model)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "version": args.version,
        "model": args.model,
        "config": cfg.__dict__,
        "traces": [],
    }
    for archetype in SUPPORTED_ARCHETYPES:
        for seed in V1_SEEDS:
            persona = generate_persona(archetype, seed=seed)
            trace = generate_trace(
                persona,
                config=cfg,
                user_sim_client=client,
                agent_client=client,
            )
            out = args.output_dir / f"{persona.persona_id}.json"
            out.write_text(trace.model_dump_json(indent=2))
            manifest["traces"].append(persona.persona_id)
            print(f"wrote {out}")

    (args.output_dir / "_manifest.json").write_text(
        json.dumps(manifest, indent=2)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
