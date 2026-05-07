# Mnemos

**A benchmark for long-horizon memory in conversational agents.**

> Status: v1 in progress. Spec is drafted; reference implementations and results forthcoming.

---

Long-running conversational agents — voice agents that re-engage, AI super-connectors, customer-support agents, AI tutors — share a problem that single-session benchmarks barely touch: **memory across sessions**. They must recall facts disclosed sessions ago, consolidate scattered low-signal mentions into coherent understanding, and update gracefully when a user's situation changes.

Mnemos evaluates these capabilities directly. It generates synthetic personas with structured disclosure schedules and update events, simulates multi-session conversation traces, and probes any memory architecture on three axes: **Recall**, **Consolidation**, and **Update**.

See [`SPEC.md`](./SPEC.md) for the full design.

## What's in the box

- A benchmark spec ([`SPEC.md`](./SPEC.md)) — the source of truth.
- A persona + trace generator (`personas/`, `traces/`) — reproducible from seeds.
- Three reference memory architectures (`baselines/`):
  - `vector_rag` — embeddings + cosine retrieval over raw turns.
  - `structured_kb` — LLM-extracted facts in a structured store.
  - `hybrid_managed` — LLM "memory manager" curating summaries + facts.
- A rubric-based LLM-judge evaluator (`evals/`).
- Versioned results (`results/`).

## Why this benchmark

Most public attention on agents focuses on single-session capability. The interesting frontier is whether an agent can sustain a *relationship* — remember you, track how you change, notice patterns, and adjust without being prompted. Mnemos targets that frontier specifically.

Existing memory benchmarks lean on synthetic long-context retrieval (LongBench, RULER, needle-in-a-haystack). Mnemos is structured around the lived shape of conversational relationships: many short sessions separated by gaps, with semi-structured personal content that evolves.

## Quickstart

```bash
git clone https://github.com/<TBD>/mnemos
cd mnemos
pip install -e .
export ANTHROPIC_API_KEY=...

# Generate the v1 trace set (deterministic from seed)
python -m mnemos.traces.generate --version v1

# Run a baseline
python -m mnemos.baselines.vector_rag --traces traces/v1

# Evaluate
python -m mnemos.evals.run --baseline vector_rag --traces traces/v1
```

## Repo layout

```
mnemos/
├── SPEC.md                  # Benchmark specification — source of truth
├── README.md
├── LICENSE
├── pyproject.toml
├── personas/                # Persona archetype templates + generation
├── traces/                  # Trace generator + versioned trace sets
├── baselines/               # Reference memory architectures
│   ├── vector_rag/
│   ├── structured_kb/
│   └── hybrid_managed/
├── evals/                   # Judge + scoring + aggregation
├── results/                 # Versioned baseline results
├── writeup/                 # Public writeup drafts
└── tests/
```

## Contributing

Highest-leverage areas: (a) additional memory architecture baselines, (b) additional persona archetypes, (c) human-written trace set, (d) judge-model alternatives, (e) reproducibility audits. See [`SPEC.md`](./SPEC.md) §11.

## Citation

If you use Mnemos in research or product work, please cite (placeholder until v1 results post is published):

```
Malladi, A. (2026). Mnemos: A benchmark for long-horizon memory in conversational agents. https://github.com/<TBD>/mnemos
```

## License

MIT.
