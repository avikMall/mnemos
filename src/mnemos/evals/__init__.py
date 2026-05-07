"""Rubric-based LLM-judge evaluator.

The judge receives a probe, the agent's response, the relevant prior
trace turns, and the persona's held-out truth annotations. It returns a
score in {-1, 0, 1, 2} per the rubrics in SPEC.md §3.

Variance control: every probe is scored 3 times; we take the median and
report inter-judge agreement.
"""

JUDGE_MODEL_DEFAULT = "claude-sonnet-4-6"  # pinned per results file
NUM_JUDGE_RUNS = 3
