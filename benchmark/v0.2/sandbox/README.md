# P0 process-isolated sandbox

This directory is the second implementation stage of Verified Delegation Benchmark v0.2.

It is deliberately stronger than `../harness/` but it is **not yet a published benchmark result**.

## Boundary

`authoritative_server.py` runs as a separate OS process and stores authoritative state in a temporary SQLite database. Systems under test and the verifier cannot read that database directly; they interact over HTTP on loopback.

The three P0 scenarios are:

- expired mandate
- replay / idempotency
- false DONE

Two deterministic systems are exercised against the same service:

- `unsafe-remote` intentionally violates the expected safety properties and must fail all three scenarios;
- `guarded-remote` applies execution-time authority checks, replay blocking and independent read-back verification and must pass all three.

The verifier is GET-only and uses a separate code path from the executor. The authoritative service records write requests so the run can demonstrate whether execution actually crossed the external-state boundary.

## Why this is still not a public result

The HTTP + SQLite service is synthetic and controlled by this repository. It creates a real process/network/state boundary suitable for testing the harness, but it is not a third-party payment, CRM or deployment sandbox and it does not represent a production autonomous-agent system.

Output is therefore labelled:

`PROCESS_SANDBOX_SELF_TEST_ONLY`

Nothing from this runner is written to `../results/`. The publication gate in `../SPEC.md` section 8 applies: a result bundle needs independently rerunnable fixtures, exact versions, raw evidence and validator-checked provenance. The one published bundle in `../results/` comes from the live GitHub Issues stage, not from this sandbox.

Run locally:

```bash
python benchmark/v0.2/sandbox/runner.py
```
