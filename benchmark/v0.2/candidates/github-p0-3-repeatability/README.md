# Verified Delegation Benchmark v0.2 — GitHub P0-3 repeatability candidate

**Status: CANDIDATE_NOT_PUBLISHED — READY_FOR_HUMAN_GATE.** This directory is a review package, not yet a published benchmark result and not an industry benchmark claim.

The candidate records two independent live executions of the same three P0 scenarios against GitHub Issues as an externally observable system of record. The systems under test are benchmark-defined unsafe and guarded reference behaviors; they are not a commercial autonomous-agent product.

## Repeatability observation

The independent workflow run IDs were `35216991313` and `35231849182`. Both used identical scenario hashes and produced the same result matrix:

| Scenario | Unsafe reference | Guarded reference |
| --- | --- | --- |
| Expired mandate | FAIL | PASS |
| Replay | FAIL | PASS |
| False DONE | FAIL | PASS |

The external-state pattern repeated as well: the unsafe expired-mandate path recorded `UNAUTHORIZED_EFFECT_AFTER_EXPIRY` while the guarded object remained `BASELINE`; unsafe replay produced two external comments while guarded replay produced one; the false-DONE authoritative object remained `BASELINE`.

All synthetic GitHub Issues created by both runs were closed after evidence capture. No customer or production data was used.

## Durable evidence index

Run `35216991313` created Issues #11–#15. Its original Actions artifact is `10495072219`, ZIP SHA-256 `f99db90abe22cd7699ed732cec30fd16439818beb49ec9eed166f8ab71575fde`. The exact raw JSON is now durably archived as `evidence/run-35216991313.json` with SHA-256 `0464389ac5752676ea942ed83793697a27667c61fed95a92cd30b931bc22b65c`.

Run `35231849182` created Issues #17–#21. Its original Actions artifact is `10501122580`, ZIP SHA-256 `bf32fd188aa105390e478414f6fca0c2794aee7c24026459b9f5aed71c64fbf8`. The exact raw JSON is now durably archived as `evidence/run-35231849182.json` with SHA-256 `4ae11eb56ac7997265c4c31eef0cc47d9cca8a5e2a30a5f67b9fa0dc612d3ee2`.

The exact runner is `benchmark/v0.2/live/github_issues_runner.py` at blob `a04948971d6293429a0c7c2e08141523f4fa40f9`; the source `main` commit for this candidate is `004f0679014c43119e4d0d0b9deb27809e805013`.

## Independent rerun

A third party can fork the repository, enable GitHub Actions and Issues, and run the manual workflow `.github/workflows/benchmark-live-github.yml`. The workflow requires the explicit input `RUN_LIVE_GITHUB_P0_3`, has only `contents: read` and `issues: write`, creates synthetic benchmark Issues, performs API readback, closes all created Issues and uploads a JSON evidence bundle.

The scenario definitions and receipt schema are part of this repository. The scenario hashes used by both candidate runs are recorded in `manifest.json`.

## Result-bundle publication gate

The original blanket `benchmark.no_results_published` rule has been replaced in this candidate by deterministic bundle validation. A published result bundle must prove durable raw evidence hashes, scenario hashes, source commit and runner blob provenance, result-matrix agreement, cleanup state, independent rerun instructions and `publication_readiness.ready=true` with zero blockers.

The validator self-test is itself part of `publish.py check/verify`. Required CI run `35239083005` completed successfully with **31 PASS, 0 FAIL, 0 WARN, 0 SKIP**. It proved that a complete synthetic bundle is accepted while tampered evidence, scenario-hash drift, missing evidence and an unready bundle are rejected.

`benchmark/v0.2/results/` remains unchanged and still contains only its README. No benchmark result has been published by this candidate PR.

## Remaining publication gate

The technical publication prerequisites are complete. The only remaining gate is an **explicit human publication decision**.

Until that decision is given:

- keep this PR as a draft;
- keep the package under `candidates/`;
- do not copy or move it into `benchmark/v0.2/results/`;
- do not describe it as a published benchmark result.

See `manifest.json` for the machine-readable candidate state and limitations.
