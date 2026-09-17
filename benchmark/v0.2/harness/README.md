# P0 executable reference harness

This directory contains the first executable implementation of the Verified
Delegation Benchmark v0.2 draft. It is deliberately small and deterministic.
It exists to prove that the benchmark can distinguish unsafe behavior from a
minimal guarded design before any public benchmark results are accepted.

## Scope

The P0 harness executes three scenarios:

1. `expired_mandate` — authority must be valid at execution time.
2. `replay` — a repeated delivery must not create a second material effect.
3. `false_done` — agent self-report must not override authoritative external state.

Two deterministic systems are exercised against the same scenarios:

- `unsafe-baseline` intentionally contains the three failure modes.
- `guarded-reference` performs execution-time authority checks, replay protection
  and independent outcome verification.

The harness exits successfully only when **all unsafe runs fail** and **all
guarded-reference runs pass**. This prevents a vacuous benchmark in which every
system is accepted.

Run it with:

```bash
python benchmark/v0.2/harness/runner.py
```

For the complete machine-readable self-test bundle:

```bash
python benchmark/v0.2/harness/runner.py --json
```

## Important: these are not published benchmark results

The output is labelled `HARNESS_SELF_TEST_ONLY`. The systems and authoritative
state are deterministic local fixtures. They are not production systems and
not third-party autonomous agents. Nothing produced by this harness is written
to `benchmark/v0.2/results/`.

Public results remain blocked until the benchmark has a reproducible external
fixture or sandbox, exact system-under-test versions, raw evidence, digests and
independent rerun instructions as required by `../SPEC.md` section 8.
