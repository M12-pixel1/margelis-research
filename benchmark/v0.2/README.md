# Verified Delegation Benchmark v0.2 (draft)

Status: **draft implementation; no public benchmark results.** The ten scenario
and receipt formats remain draft. Two executable P0 stages now test the benchmark
machinery itself; neither is a production-system benchmark result.

| Path | Content |
| --- | --- |
| [`SPEC.md`](SPEC.md) | Boundary, terms, scenario and receipt formats, metric computation, publication rule |
| [`scenarios/`](scenarios/) | Ten machine-readable adversarial scenario definitions (YAML) |
| [`schemas/scenario.schema.json`](schemas/scenario.schema.json) | JSON Schema for scenario files |
| [`schemas/receipt.schema.json`](schemas/receipt.schema.json) | Draft JSON Schema for outcome receipts |
| [`schemas/examples/`](schemas/examples/) | Synthetic receipt examples (not results) |
| [`harness/`](harness/) | Deterministic P0 self-test harness: expired mandate, replay, false DONE |
| [`sandbox/`](sandbox/) | Process-isolated HTTP + SQLite authoritative-state sandbox for the same P0 cases |
| [`results/`](results/) | Empty until independent rerun of an actual system-under-test is possible |

Validate the benchmark definitions:

```bash
python tools/publish.py check-benchmark
```

Run the deterministic P0 harness:

```bash
python benchmark/v0.2/harness/runner.py
```

Run the process-isolated P0 sandbox:

```bash
python benchmark/v0.2/sandbox/runner.py
```

Both stages must reject the intentionally unsafe baseline and accept the guarded
reference implementation. Their outputs are labelled `HARNESS_SELF_TEST_ONLY`
and `PROCESS_SANDBOX_SELF_TEST_ONLY`; neither writes to `results/`.

The process sandbox gives the executor and verifier a real HTTP boundary and keeps
authoritative state in a separate SQLite-backed service process, but it remains a
synthetic service controlled by this repository. It is therefore evidence that the
benchmark machinery survives a process/network/state boundary, not evidence about a
third-party or production autonomous-agent system.

The benchmark is derived from
[Margelis Research Note 001](../../research/001/). Public Verified Delegation
Benchmark v0.2 results will be published only when an actual system-under-test
can be independently rerun with its fixtures, versions and raw evidence.
