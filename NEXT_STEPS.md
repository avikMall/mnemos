# Mnemos — next steps

A working log of where we are and what comes next. This is for our future selves; the public-facing artifacts are `SPEC.md` and `README.md`.

## Where we are (end of session 2)

Done:
- `SPEC.md` v1 drafted — three eval axes (Recall, Consolidation, Update), persona model, trace schema, scoring rubrics, judge model plan.
- Repo scaffold: README, LICENSE (MIT), pyproject.toml, .gitignore, package layout under `src/mnemos/`.
- Core data types in `mnemos.types` (Persona, Fact, UpdateEvent, Session, Turn, Probe, Trace, ProbeScore) with passing schema tests.
- `mnemos.protocol.MemorySystem` — the two-method contract every baseline implements.
- `mnemos.personas.templates` — archetype templates. v1 fully specifies `early_stage_founder`; the other four are registered in `Archetype` enum and ready for templating.
- `mnemos.personas.generate` — deterministic persona generation.
- `mnemos.probes.templates` — probe templates per axis (Recall direct/indirect/negative, Consolidation, Update with latency offsets).
- `mnemos.probes.generate` — deterministic probe generation. Resolves rubric targets from a persona, anchors Update probes to update events that actually fired, clips latency variants that would land beyond the trace.
- 21 unit tests pass across types, persona generation, and probe generation.

The deterministic data layer is complete. `generate_persona(EARLY_STAGE_FOUNDER, seed=2)` always produces the same Asha Patel; `generate_probes(persona, num_sessions=6)` always produces the same 13 probes spread across the three axes. Repo is live at https://github.com/avikMall/mnemos.

## Up next, in order

### 1. Trace generator (task #9)

This is the first part that touches an LLM. Plan:

- A **user simulator** prompt that takes a persona snapshot + the disclosure plan for the current session + scheduled updates. It produces user turns that disclose what's scheduled in a natural, conversational way without breaking character or front-running future disclosures.
- A **stand-in agent** prompt that's deliberately vanilla — Mnemos is not testing this agent; it's just generating realistic conversational scaffolding so the memory system gets something to ingest. Prompt should be Boardy-shaped (warm, asks open questions) but NOT use Boardy's actual voice.
- Each session: alternating user/agent turns until either a turn budget is hit or the user simulator decides the session has reached a natural close.
- Pin model version in the trace JSON. Re-runs with the same model + seed should produce identical (or near-identical) traces; record any nondeterminism observed.
- Cost guardrail: cap session turn count at ~12.

Open question: do we want the stand-in agent to be the *same* model as the agent under test, or a different one? Lean toward "same family but vanilla prompting" — keeps cost predictable and avoids contamination.

### 2. Three baseline memory systems (task #4)

All three implement `MemorySystem` from `mnemos.protocol`.

**`baselines/vector_rag/`**
- Embed each turn (or sliding window of turns) on `ingest`.
- On `respond`, embed the probe + current session context, retrieve top-k by cosine, stuff into a prompt, call the answering LLM.
- FAISS or numpy dot product — keep it bare-bones.
- Knobs to expose: chunk granularity (turn vs. session vs. windowed), k, embedding model.

**`baselines/structured_kb/`**
- After each session, run an extractor LLM that pulls structured claims: `(entity, relation, value, session_id, confidence)`.
- Store in a simple sqlite or in-memory table. On update events, mark old facts as superseded by ID, mirroring our schema.
- On `respond`, run a query-planner LLM that translates the probe into a KB lookup, fetches matching rows, then composes a response.

**`baselines/hybrid_managed/`**
- After each session, an LLM "memory manager" decides what to do: write a session summary, extract specific facts, mark prior facts as superseded, or drop things.
- On `respond`, retrieve relevant summaries + facts and answer.
- This is the most "agentic" memory architecture and we'd expect it to win on Update and lose on simple Recall (its summarization may compress away precise facts).

### 3. Evaluator (task #5)

Important detail: the evaluator must resolve fact values *as of the probe's session*, walking `persona.update_events` in order. A recall probe at session 6 about `co_founder_name`, on a persona where `cofounder_departs` fired in session 6, expects the post-update value as truth. Add this resolution helper to `mnemos.evals` when building the judge prompt.

- Judge prompt template per axis (rubrics from SPEC §3).
- 3 runs per probe, median, log inter-judge agreement.
- Aggregate to per-axis means, per-archetype breakdowns, latency-binned numbers for Update.
- Persist results to `results/<run-name>/results.json` with all model/version/SHA metadata.

### 4. Writeup (task #6)

Structure:
1. The problem (single-session vs. relationship)
2. Why existing memory benchmarks miss this
3. Mnemos design (link to SPEC)
4. Three baselines
5. Results table + per-axis discussion
6. Where each architecture wins and loses, with examples
7. Real-world reflection — including a constructive Boardy paragraph drawn from prior calls
8. Future work and call for contributors

Tone targets: technical, honest about limitations, not snarky. The Boardy paragraph should feel like a fan's note, not a critique.

### 5. Verification + public push (task #7)

- Clean checkout, regenerate trace v1 set from seeds, re-run baselines, confirm identical aggregates (within judge variance).
- Have a friend (or two) read the writeup specifically for tone in the Boardy section.
- Pick a name (Mnemos is the working title; verify GitHub org availability and a domain if we want one).
- Publish: GitHub repo public, blog post live, X post tagging Andrew framed as contribution-not-pitch.

## Risk register

- **Trace realism.** A user simulator powered by an LLM has its own quirks — repetitive phrasing, over-explicit disclosures. We will need to read a sample of generated traces and likely tighten the simulator prompt. Plan: hand-review 10 traces before running the full v1 generation.
- **Judge variance.** Rubric-based scoring with LLM judges is famously noisy. The 3-run-and-median strategy plus inter-judge α metric is the v1 mitigation. If α is low (<0.6) on any axis, we need to either tighten the rubric or add a second judge family.
- **Boardy section tone.** This is the highest-stakes paragraph in the writeup. It needs to be specific (drawn from real calls) and constructive (not "here's what's wrong"). Plan: write it last, after results are in, and have at least one outside reader specifically critique that paragraph before publishing.
- **Cost.** Full v1 run = ~50 personas × 6 sessions × ~20 LLM turns × 3 baselines × probe-time inference + 3 judge runs × ~3,000 probes. Need a cost estimate before locking the v1 trace size.

## Decisions deferred

- Project name (Mnemos is the working title; alternatives considered: LongMemo-Bench, Anamnesis, Throughline).
- Whether to ship a small (10-trace) "starter set" alongside v1 for people who don't want to pay to regenerate.
- Whether to bind to a specific judge family or report results with two (Claude + GPT-class).
