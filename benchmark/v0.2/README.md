# Verified Delegation Benchmark v0.2 (draft)

Status: **draft specification only.** No implementation, fixtures, baselines or
results are published here.

| Path | Content |
| --- | --- |
| [`SPEC.md`](SPEC.md) | Boundary, terms, scenario and receipt formats, metric computation, publication rule |
| [`scenarios/`](scenarios/) | Ten machine-readable adversarial scenario definitions (YAML) |
| [`schemas/scenario.schema.json`](schemas/scenario.schema.json) | JSON Schema for scenario files |
| [`schemas/receipt.schema.json`](schemas/receipt.schema.json) | Draft JSON Schema for outcome receipts |
| [`schemas/examples/`](schemas/examples/) | Synthetic receipt examples (not results) |
| [`results/`](results/) | Empty until independent rerun is possible |

Validate everything:

```bash
python tools/publish.py check-benchmark
```

The benchmark is derived from
[Margelis Research Note 001](../../research/001/). The Verified Delegation
Benchmark v0.2 release will be published only once an independent rerun is
possible.
