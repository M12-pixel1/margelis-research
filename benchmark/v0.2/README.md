# Verified Delegation Benchmark v0.2 (draft)

Status: **draft implementation; no public benchmark results.** The ten scenario
and receipt formats remain draft. A deterministic P0 reference harness now
executes three scenarios to test the benchmark machinery itself; it is not a
production-system benchmark result.

| Path | Content |
| --- | --- |
| [`SPEC.md`](SPEC.md) | Boundary, terms, scenario and receipt formats, metric computation, publication rule |
| [`scenarios/`](scenarios/) | Ten machine-readable adversarial scenario definitions (YAML) |
| [`schemas/scenario.schema.json`](schemas/scenario.schema.json) | JSON Schema for scenario files |
| [`schemas/receipt.schema.json`](schemas/receipt.schema.json) | Draft JSON Schema for outcome receipts |
| [`schemas/examples/`](schemas/examples/) | Synthetic receipt examples (not results) |
| [`harness/`](harness/) | Executable P0 self-test harness: expired mandate, replay, false DONE |
| [`results/`](results/) | Empty until independent rerun of an actual system-under-test is possible |

Validate the benchmark definitions:

```bash
python tools/publish.py check-benchmark
```

Run the P0 executable harness:

```bash
python benchmark/v0.2/harness/runner.py
```

The harness must reject the intentionally unsafe baseline and accept the guarded
reference implementation. Its output is labelled `HARNESS_SELF_TEST_ONLY` and
is never written to `results/`.

The benchmark is derived from
[Margelis Research Note 001](../../research/001/). Public Verified Delegation
Benchmark v0.2 results will be published only when an actual system-under-test
can be independently rerun with its fixtures, versions and raw evidence.
