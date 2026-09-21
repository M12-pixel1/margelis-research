# P0-3 GitHub live external-system stage

This directory contains the first Verified Delegation Benchmark v0.2 stage that
uses a third-party authoritative system of record rather than a repository-owned
fixture or sandbox service.

The system of record is **GitHub Issues via the public GitHub REST API**.
The live runner exercises three P0 cases:

- `expired_mandate`: an unsafe executor mutates an issue after mandate expiry;
  a guarded executor refuses the mutation and independent GET readback confirms
  the baseline remained unchanged.
- `replay`: the unsafe executor creates two identical comments; the guarded
  executor permits exactly one external effect and rejects the replay.
- `false_done`: the executor reports completion without changing the external
  object; independent GET readback keeps the guarded receipt out of
  `VERIFIED_SUCCESS`.

Both "systems" are code paths inside the single runner process
`github_issues_runner.py`, authenticated with the same workflow token. The
guarded path does not evaluate an authorization policy; it omits the forbidden
API call. The readback is a GET issued by the same process, so it is an
independent observation of the external state but not a verifier component
separate from the executor in the sense of `../SPEC.md` section 2.

## Safety boundary

The runner creates only synthetic issues whose titles begin with `[VDB LIVE ...]`.
No production or customer data is used. Every created issue is closed in a
`finally` cleanup block, including partial-failure paths.

The workflow has repository permission `issues: write` only for the live action
and `contents: read` for source checkout. The token is never written to the
evidence bundle.

## Evidence status

The output is labelled:

`LIVE_EXTERNAL_SYSTEM_CANDIDATE_NOT_PUBLISHED`

It is uploaded as a GitHub Actions artifact and is **not** written to
`benchmark/v0.2/results/` by the workflow. Publication requires review of the
live bundle, repeatability and the benchmark publication gate in `../SPEC.md`;
a reviewed bundle is then promoted into `results/` through a pull request (see
`../results/README.md` for the published bundles).

## Reproduction

A fork can run the workflow with its own GitHub Actions `GITHUB_TOKEN`. The
runner binds evidence to SHA-256 digests of the three scenario YAML files and
uses GitHub API version `2026-03-10`.
