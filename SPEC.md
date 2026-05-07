# Mnemos

**A benchmark for long-horizon memory in conversational agents.**

Status: v1 draft, spec-only. Reference implementations and results forthcoming.

---

## 1. Problem

A new generation of conversational agents talks to the same user repeatedly over weeks or months — voice agents that re-engage, AI super-connectors that build relationships, customer-support agents that span tickets, AI tutors that follow a learner across a course, sales agents that nurture leads through long cycles. These agents share a structural problem that single-session benchmarks barely touch: **memory across sessions**.

Concretely, an agent in production faces three demands at once:

1. **Recall** — when a user mentions today that they "had that conversation with my co-founder," the agent should know who the co-founder is and what the relevant prior context was, even if it was disclosed three sessions ago.
2. **Consolidation** — across many low-signal mentions ("we're hiring slowly," "I'm worried about runway," "Series A is taking forever"), the agent should be able to form higher-level understanding ("this user is in a stressed fundraising window") without being told explicitly.
3. **Update** — when a user's situation changes ("I actually left that company last month"), the agent should track the evolution and adjust downstream reasoning, rather than confabulate from stale state or stick rigidly to the original fact.

Existing memory benchmarks (LongBench, RULER, MemGPT's evaluation suite, and most "needle-in-a-haystack" tests) lean heavily on synthetic long-context retrieval. They are not designed around the lived structure of conversational relationships: many short sessions, separated by gaps, with semi-structured personal content that evolves. Mnemos aims to fill that gap.

---

## 2. Scope

**In scope (v1):**
- Long-horizon memory in multi-session text conversations between a user and an agent.
- Three eval axes: Recall, Consolidation, Update.
- Synthetic personas and conversation traces, generated from controlled seeds for reproducibility.
- Reference implementations of three memory architectures (vector RAG, structured KB, hybrid LLM-managed).
- LLM-as-judge scoring with rubric-driven prompts.

**Out of scope (v1):**
- Voice / audio modality (we operate on transcripts).
- Multi-user matching and decision quality (a separate benchmark; deliberately deferred).
- Conversational quality / "did the agent ask good questions" (also separate).
- Selective forgetting / privacy-respecting deletion (planned for v2).

---

## 3. Eval axes

### 3.1 Recall

**Definition.** Given a specific fact stated by the user in some prior session, can the agent retrieve it (verbatim or paraphrased) when the current session asks for it?

**Probe types.**
- *Direct ask:* "Remind me what I told you last time about X."
- *Indirect dependency:* The current session's coherent response requires retrieving fact X. (E.g., user references "my brother" without naming him; agent should remember the name from session 2.)
- *Negative recall:* User asks about a topic that was never discussed; the agent should say so rather than confabulate.

**Scoring (per probe).**
- **2** — fact recalled correctly and grounded in the right prior session.
- **1** — fact recalled approximately or partially.
- **0** — fact not recalled, or hallucinated.
- **−1** — confabulation: agent invents a "memory" that was never present in the trace.

Negative confabulation is penalized harder than mere forgetting; a memory system that hallucinates is worse than one that admits it doesn't know.

### 3.2 Consolidation

**Definition.** Can the agent synthesize patterns across many low-signal mentions into useful higher-level understanding?

**Probe types.**
- *Latent theme detection:* Five sessions contain scattered mentions consistent with a single underlying state (e.g., job stress, fundraising anxiety, romantic difficulty). Agent is asked an open question; answer is scored on whether it surfaces the latent theme.
- *Relational inference:* Multiple sessions mention different people in the user's life. Agent is asked who is "closest" / "most influential" — scoring uses a held-out persona-truth annotation.
- *Goal evolution tracking:* Across sessions, the user's stated goals shift subtly. Agent is asked to summarize "what you're working on now"; scored against the persona's current declared goal vector.

**Scoring (per probe).**
- **2** — agent surfaces the correct latent pattern and grounds it in specific prior content.
- **1** — agent gestures at the pattern but doesn't ground it, or partially correct.
- **0** — agent restates surface facts with no synthesis.
- **−1** — synthesis is wrong in a way the user would notice (claims a theme not present).

### 3.3 Update

**Definition.** When information changes between sessions, does the agent track the change and reason from current state, rather than from stale state or a confused mixture?

**Probe types.**
- *Hard update:* User explicitly says "I left that job" / "we broke up" / "we pivoted." Later, a probe references the topic; the agent should treat the new state as canonical.
- *Soft update:* User's framing shifts gradually (positive → negative → ambivalent about a project). Probed in a way that requires the current frame.
- *Contradiction without resolution:* User contradicts themselves between sessions but never explicitly retracts. Agent should either recognize ambiguity ("I've heard you describe this differently in different conversations — which feels right today?") or reason from the most recent.
- *Latency check:* Update is communicated in session N; probe is in session N+k for varying k. Quality should not degrade strongly with k.

**Scoring (per probe).**
- **2** — agent reasons from the post-update state, ideally also acknowledging the change.
- **1** — agent reasons from the post-update state without acknowledgment, or shows mild conflation.
- **0** — agent reasons from stale state (acts as if update never happened).
- **−1** — agent reasons from a confused mixture or hallucinates a different update.

---

## 4. Persona model

A **persona** is a structured object that defines a synthetic user across the lifespan of a benchmark run. It includes:

- **Static profile**: name, occupation, location, fixed background facts.
- **Dynamic state vector**: goals, relationships, projects, emotional valence — each with timestamps for when they were established and (optionally) when they changed.
- **Disclosure plan**: a schedule of what topics are introduced in which session, at what level of explicitness (direct vs. oblique).
- **Update events**: timestamped state transitions (job change, relationship change, goal pivot).
- **Held-out truth annotations**: ground-truth labels used by the evaluator, never shown to the agent.

Personas are generated from seed + persona-archetype templates. Archetypes for v1 include: *early-stage founder*, *mid-career operator considering a switch*, *researcher seeking collaborators*, *job-seeker in a slump*, *recently-funded founder hiring aggressively*. Archetypes are deliberately Boardy-adjacent (the user types Boardy talks to) but the framework generalizes to any conversational-relationship agent.

---

## 5. Conversation traces

A **trace** is a sequence of sessions for one persona. Each session is a turn-by-turn dialogue (user ↔ agent) generated by a *user simulator* — itself an LLM driven by the persona's disclosure plan, dynamic state, and any update events scheduled for that session.

**Trace JSON schema (v1):**

```json
{
  "trace_id": "trace_001",
  "persona_id": "founder_early_seed_007",
  "sessions": [
    {
      "session_id": "s1",
      "timestamp": "2025-01-10T15:00:00Z",
      "turns": [
        {"role": "user", "text": "..."},
        {"role": "agent", "text": "..."}
      ],
      "scheduled_disclosures": ["co_founder_name", "current_project"],
      "scheduled_updates": []
    },
    ...
  ],
  "probes": [
    {
      "probe_id": "p1",
      "axis": "recall",
      "after_session": "s4",
      "input": "Remind me what I told you about my co-founder.",
      "rubric_targets": ["co_founder_name", "co_founder_relationship"]
    },
    ...
  ]
}
```

Traces are deterministic given (persona_id, generator_version, seed). The benchmark ships with a fixed v1 trace set so results are comparable across systems; researchers can also generate fresh traces from new seeds for held-out evaluation.

---

## 6. The agent under test

A **memory system** plugged into Mnemos exposes two interfaces:

- `ingest(session)` — called after each session in the trace; lets the system update its memory store however it wants.
- `respond(probe, current_session_context)` — given a probe and the current partial session, produces a textual response. The probe's content and the current session may reference past content; the system is responsible for any retrieval.

This separation matters: it lets us evaluate any memory architecture (from "stuff everything into the prompt" to MemGPT-style hierarchical memory to graph-structured KBs) on equal footing.

The benchmark provides three reference implementations:

1. **vector_rag** — embeds each turn, retrieves top-k by cosine similarity at probe time.
2. **structured_kb** — uses an LLM to extract entities, claims, and updates after each session into a structured store; queries the store at probe time.
3. **hybrid_managed** — an LLM "memory manager" decides per-session what to summarize, what to store, and what to discard; combines a summary store with a fact store.

---

## 7. Scoring

Scoring is **rubric-based LLM-as-judge** with the rubric pinned per probe (see §3). The judge:

- Receives the probe, the agent's response, the persona's held-out truth annotations, and the relevant prior trace turns.
- Returns a score in {−1, 0, 1, 2} plus a one-sentence justification.
- Is run with temperature 0 and a fixed model version.

To control judge variance, every probe is scored 3 times and the median is taken. We also report inter-judge agreement (Krippendorff's α) and any probes with disagreement get manual annotation in the v1 results.

**Aggregate metrics:**
- Per-axis mean score and standard error.
- Per-archetype breakdown.
- Per-probe-difficulty breakdown (for Update: latency-binned k).
- A composite "Mnemos score" — an unweighted mean across the three axes — reported alongside the per-axis numbers but never alone.

We deliberately avoid a single headline number that could be over-optimized.

---

## 8. Reproducibility

- Trace v1 set: 50 personas × ~6 sessions × ~10 probes ≈ ~3,000 scored items. Versioned and committed.
- Seeds are exposed; trace regeneration is deterministic.
- Judge model and version are pinned in `evals/judge.py` and reported in every results file.
- Results files include git SHA, model versions for both agent and judge, and the trace set version.

---

## 9. Why this matters in the real world

Most public attention on AI agents goes to single-session capability — can the agent solve this problem, write this code, complete this task. The interesting frontier is whether agents can sustain a relationship: remember you, track how you change, notice patterns, and adjust without being prompted.

This is the hard problem behind every AI coding agent that gets re-invoked on the same codebase, every customer-support agent that handles repeat tickets, every voice agent that calls a user back. It is also the problem behind a smaller but interesting class: **AI super-connectors** like Boardy, who talk to thousands of people and need to remember enough about each to be genuinely useful when those people resurface.

The Mnemos design draws on observation of one such system. I've talked to Boardy multiple times, and the experience makes the memory question concrete in a way that running synthetic benchmarks alone does not. A constructive note on what I observed, and where it intersects with the axes above, will appear in the public writeup once results are in.

---

## 10. Open questions for v1

- **Judge model.** Default plan is to use a Claude model (Sonnet-class, pinned version) as judge. Should we also report results with a second judge family for cross-validation? (Probably yes, even if just on a 10% subset.)
- **Persona diversity.** v1 archetypes skew toward tech / early-stage. Should v1.1 include a non-tech archetype set?
- **Realism of synthetic traces.** A user simulator powered by an LLM will have its own quirks. Should we mix in a small handful of human-written traces for validation?
- **Cost.** Running all baselines on the full trace set is non-trivial in API spend. We need a cost estimate before locking the v1 trace size.

---

## 11. Contributing

Contributions welcome. Highest-leverage areas: (a) additional memory architecture baselines, (b) additional persona archetypes, (c) human-written trace set, (d) judge model alternatives, (e) reproducibility audits.
