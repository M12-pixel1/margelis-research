# Reproduce the reference demonstration

Use the public source commit `d6f532dfcfa28df7828dfec6db63a0f752d3567b` in `M12-pixel1/margelis-research`. The source files were byte-checked against their Git blob identifiers before execution. No reference logic was modified.

Run in a disposable local workspace. Only the process sandbox opens a loopback HTTP port; no external service or credential is needed.

```bash
git clone https://github.com/M12-pixel1/margelis-research.git
cd margelis-research
git checkout d6f532dfcfa28df7828dfec6db63a0f752d3567b
python -m venv .venv
. .venv/bin/activate
python -m pip install PyYAML==6.0.3 jsonschema==4.26.0 attrs==26.1.0 jsonschema-specifications==2025.9.1 referencing==0.37.0 rpds-py==2026.9.1 typing-extensions==4.16.0
python benchmark/v0.2/harness/runner.py --json > harness-run-01.json
python benchmark/v0.2/harness/runner.py --json > harness-run-02.json
python benchmark/v0.2/sandbox/runner.py
```

The original sandbox CLI prints a summary. To capture the full, unchanged sandbox result in JSON, use its existing `run_all` function:

```bash
python -c "import runpy,json; d=runpy.run_path('benchmark/v0.2/sandbox/runner.py'); print(json.dumps(d['run_all'](),indent=2,sort_keys=True))" > sandbox-run-01.json
python -c "import runpy,json; d=runpy.run_path('benchmark/v0.2/sandbox/runner.py'); print(json.dumps(d['run_all'](),indent=2,sort_keys=True))" > sandbox-run-02.json
```

The reproduction environment used Python 3.12.14. Exact imported dependency versions and source SHA-256 digests are in `evidence/provenance.json`. The dependency installation above mirrors this reproduction, not the full publication-pipeline lock.

Expected outcome: every guarded row has `pass: true`; every unsafe row has `pass: false`. The latter is the intended negative control. Inspect `receipt`, `external_state` and `reasons`, rather than interpreting a process exit code alone as task completion.

Both harness outputs should be identical for the fixed source and environment. Sandbox receipt values can contain run-specific details; compare the scenario decisions and authoritative synthetic state rather than requiring cross-run byte identity.

There are three scenario types. Two repeats at each stage do not create twelve independent scenario types, a population failure-rate estimate, or an independent replication of a deployed agent.
