# Verified Delegation Benchmark v0.2 — GitHub P0-3 repeatability result

**Status: PUBLISHED_RESULT.** This is a published Verified Delegation Benchmark v0.2 result bundle for the bounded GitHub Issues P0-3 experiment. It is not an industry-wide benchmark claim and does not establish generalization beyond the stated system and scenarios.

The bundle records two repeated live executions of the same three P0 scenarios against GitHub Issues as an externally observable system of record. Both runs were started from this repository by its owner; they demonstrate repeatability, not an independent reproduction by a third party. The systems under test are benchmark-defined unsafe and guarded reference behaviors; they are not a commercial autonomous-agent product.

## Repeatability observation

The two workflow run IDs were `35216991313` and `35231849182`. Both used identical scenario hashes and produced the same result matrix:

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

The exact runner is `benchmark/v0.2/live/github_issues_runner.py` at blob `a04948971d6293429a0c7c2e08141523f4fa40f9`; the `main` commit that carries this runner and the workflow is `004f0679014c43119e4d0d0b9deb27809e805013`.

How the two runs were actually triggered (recorded from the GitHub Actions run metadata; see `runs[]` in `manifest.json`): run `35216991313` was a `push` event on branch `benchmark/v0.2-p0-github-live` at commit `bd189fd` (tag `vdb-run-35216991313`, on `main`); run `35231849182` was a `push` event on branch `benchmark/v0.2-p0-github-repeat-2` at commit `1625b73` (tag `vdb-run-35231849182`, not part of the `main` history), through a copy of the workflow named `benchmark-live-github-repeat-2.yml`. Neither run went through the `workflow_dispatch` confirmation gate that the workflow on `main` has today. The runner blob is identical at both run commits and at the `main` commit above, so the code that executed is exactly the one recorded.

Both evidence files carry `result_status: LIVE_EXTERNAL_SYSTEM_CANDIDATE_NOT_PUBLISHED` and a `publication_warning`. The runner writes these labels at execution time, before any publication decision, and the files are kept byte-exact so the SHA-256 digests above remain valid; the publication status of this bundle is the `status` field of `manifest.json`. The original Actions artifacts are retained until 2026-12-16; after that only the archived JSON files and their digests remain verifiable.

## Independent rerun

A third party can fork the repository, enable GitHub Actions and Issues, and run the manual workflow `.github/workflows/benchmark-live-github.yml`. The workflow requires the explicit input `RUN_LIVE_GITHUB_P0_3`, has only `contents: read` and `issues: write`, creates synthetic benchmark Issues, performs API readback, closes all created Issues and uploads a JSON evidence bundle.

The scenario definitions and receipt schema are part of this repository. The scenario hashes used by both runs are recorded in `manifest.json`.

No third-party rerun has been performed or reported as of publication. A rerun in a fork executes the same runner against the fork's own Issues and produces a new evidence bundle; it does not re-observe Issues #11–#15 and #17–#21, which remain readable (closed) in this repository for inspection.

## Result-bundle publication gate

The original blanket `benchmark.no_results_published` rule was replaced in pull request #22 (commit `d6207cd`) by deterministic bundle validation (`tools/mrpub/benchmark_results.py`). The validator checks that the raw evidence files match the SHA-256 digests in the manifest, that the scenario hashes match the scenario files, that the source commit and runner blob resolve in the repository (and, where recorded, that each run's head commit carries the same runner), that all listed runs agree on the result matrix, that the cleanup evidence shows every created object closed, that at least two runs with distinct IDs exist, that the README has an "Independent rerun" section naming the exact runner and workflow paths, and that `publication_readiness.ready` is `true` with no blockers. It does not execute the rerun instructions, and `ready` is a flag set by the publisher; the publication decision itself is the pull-request merge recorded below.

The validator self-test is part of `publish.py check/verify`. Required CI run `35239083005` (pull-request head `c5d8dd9`, before this bundle existed) reported 31 PASS, 0 FAIL, 0 WARN, 0 SKIP and showed that a complete synthetic bundle is accepted while tampered evidence, scenario-hash drift, missing evidence and an unready bundle are rejected. The required run that validated this published bundle on `main` is `35251754251` (merge commit `7e4b7744`).

This validated bundle is published at `benchmark/v0.2/results/github-p0-3-repeatability-2026-09-17/` with its durable raw evidence and provenance.

## Publication decision

Published by the repository owner's merge of pull request [#22](https://github.com/M12-pixel1/margelis-research/pull/22) into the protected `main` branch on 2026-09-17 (merge commit `7e4b7744`), after two repeated live runs, durable raw-evidence archival, deterministic result-bundle validation, negative validator tests and a green required CI run. The merge record is the evidence of that decision.

The limitations above remain part of the published result and must travel with any citation or comparison.
