"""Deterministic validation for published Verified Delegation Benchmark result bundles."""
from __future__ import annotations

import json
import re
from pathlib import Path

from .common import PipelineError, git, load_json, sha256_file

EXPECTED_BENCHMARK = "Verified Delegation Benchmark v0.2"
PUBLISHED_STATUS = "PUBLISHED_RESULT"
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _safe_repo_path(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    p = Path(value)
    if p.is_absolute() or ".." in p.parts:
        return None
    return p.as_posix()


def _load_json(path: Path, problems: list[str], label: str):
    try:
        return load_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        problems.append(f"{label}: cannot load JSON: {type(exc).__name__}: {exc}")
        return None


def _validate_bundle(root: Path, bundle: Path) -> list[str]:
    problems: list[str] = []
    label = bundle.name

    if not bundle.is_dir():
        return [f"{label}: result entry must be a directory"]

    allowed = {"README.md", "manifest.json", "evidence"}
    unexpected = sorted(p.name for p in bundle.iterdir() if p.name not in allowed)
    if unexpected:
        problems.append(f"{label}: unexpected top-level entries: {unexpected}")

    readme = bundle / "README.md"
    manifest_path = bundle / "manifest.json"
    evidence_dir = bundle / "evidence"
    for required in (readme, manifest_path, evidence_dir):
        if not required.exists():
            problems.append(f"{label}: missing {required.name}")
    if problems:
        return problems

    manifest = _load_json(manifest_path, problems, label)
    if manifest is None:
        return problems

    if manifest.get("status") != PUBLISHED_STATUS:
        problems.append(f"{label}: status must be {PUBLISHED_STATUS}")
    if manifest.get("benchmark") != EXPECTED_BENCHMARK:
        problems.append(f"{label}: benchmark must be {EXPECTED_BENCHMARK!r}")
    if manifest.get("result_id") != label:
        problems.append(f"{label}: result_id must equal directory name")

    readiness = manifest.get("publication_readiness") or {}
    if readiness.get("ready") is not True or readiness.get("blockers") != []:
        problems.append(f"{label}: publication_readiness must be ready=true with zero blockers")

    limitations = manifest.get("limitations")
    if not isinstance(limitations, list) or not limitations or not all(isinstance(x, str) and x.strip() for x in limitations):
        problems.append(f"{label}: limitations must be a non-empty list of strings")

    source = manifest.get("source") or {}
    commit = source.get("main_commit")
    runner_path = _safe_repo_path(source.get("runner_path"))
    workflow_path = _safe_repo_path(source.get("workflow_path"))
    runner_blob_sha = source.get("runner_blob_sha")
    if not isinstance(commit, str) or not HEX40.fullmatch(commit):
        problems.append(f"{label}: source.main_commit must be a 40-hex commit SHA")
    if runner_path is None or workflow_path is None:
        problems.append(f"{label}: source runner/workflow paths must be safe repository-relative paths")
    if not isinstance(runner_blob_sha, str) or not HEX40.fullmatch(runner_blob_sha):
        problems.append(f"{label}: source.runner_blob_sha must be a 40-hex Git blob SHA")
    if isinstance(commit, str) and HEX40.fullmatch(commit) and runner_path and workflow_path:
        try:
            observed_blob = git("rev-parse", f"{commit}:{runner_path}")
            git("cat-file", "-e", f"{commit}:{workflow_path}")
            if observed_blob != runner_blob_sha:
                problems.append(f"{label}: runner blob {observed_blob} != manifest {runner_blob_sha}")
        except PipelineError as exc:
            problems.append(f"{label}: source provenance not resolvable: {exc}")

    scenario_hashes = manifest.get("scenario_hashes")
    if not isinstance(scenario_hashes, dict) or not scenario_hashes:
        problems.append(f"{label}: scenario_hashes must be a non-empty object")
        scenario_hashes = {}
    else:
        for scenario, claimed in sorted(scenario_hashes.items()):
            scenario_path = root / "scenarios" / f"{scenario}.yaml"
            if not scenario_path.exists():
                problems.append(f"{label}: scenario file missing for {scenario}")
                continue
            expected = "sha256:" + sha256_file(scenario_path)
            if claimed != expected:
                problems.append(f"{label}: scenario hash mismatch for {scenario}: {claimed} != {expected}")

    matrix = manifest.get("result_matrix")
    matrix_by_scenario: dict[str, dict] = {}
    if not isinstance(matrix, list) or not matrix:
        problems.append(f"{label}: result_matrix must be a non-empty list")
    else:
        for row in matrix:
            if not isinstance(row, dict) or not isinstance(row.get("scenario"), str):
                problems.append(f"{label}: malformed result_matrix row")
                continue
            scenario = row["scenario"]
            if scenario in matrix_by_scenario:
                problems.append(f"{label}: duplicate result_matrix scenario {scenario}")
            matrix_by_scenario[scenario] = row
            if row.get("unsafe") not in {"PASS", "FAIL"} or row.get("guarded") not in {"PASS", "FAIL"}:
                problems.append(f"{label}: {scenario} matrix values must be PASS/FAIL")
            if row.get("runs_agree") is not True:
                problems.append(f"{label}: {scenario} runs_agree must be true")
        if set(matrix_by_scenario) != set(scenario_hashes):
            problems.append(f"{label}: result_matrix scenarios must equal scenario_hashes keys")

    repeatability = manifest.get("repeatability") or {}
    for field in ("scenario_hashes_identical", "acceptance_matrix_identical", "external_state_pattern_identical"):
        if repeatability.get(field) is not True:
            problems.append(f"{label}: repeatability.{field} must be true")

    runs = manifest.get("runs")
    if not isinstance(runs, list) or len(runs) < 2:
        problems.append(f"{label}: at least two repeated runs are required")
        runs = []
    run_ids: set[str] = set()
    for run in runs:
        if not isinstance(run, dict):
            problems.append(f"{label}: malformed run entry")
            continue
        run_id = str(run.get("run_id", ""))
        if not run_id.isdigit():
            problems.append(f"{label}: run_id must be numeric")
            continue
        if run_id in run_ids:
            problems.append(f"{label}: duplicate run_id {run_id}")
        run_ids.add(run_id)

        head = run.get("head_sha")
        if head is not None:
            # the commit each run actually executed must be recorded and must carry the same runner
            if not isinstance(head, str) or not HEX40.fullmatch(head):
                problems.append(f"{label}: run {run_id} head_sha must be a 40-hex commit SHA")
            elif runner_path and isinstance(runner_blob_sha, str):
                try:
                    if git("rev-parse", f"{head}:{runner_path}") != runner_blob_sha:
                        problems.append(f"{label}: run {run_id} executed a different runner than source.runner_blob_sha")
                except PipelineError:
                    problems.append(f"{label}: run {run_id} head commit {head[:7]} is not fetchable "
                                    f"(push a tag such as vdb-run-{run_id} pointing at it)")
            if run.get("event") not in {"push", "workflow_dispatch", "schedule", "pull_request"}:
                problems.append(f"{label}: run {run_id} event must record how the run was triggered")

        raw_digest = run.get("raw_evidence_json_sha256")
        if not isinstance(raw_digest, str) or not HEX64.fullmatch(raw_digest):
            problems.append(f"{label}: run {run_id} raw_evidence_json_sha256 must be 64 hex")
            continue
        evidence_path = evidence_dir / f"run-{run_id}.json"
        if not evidence_path.exists():
            problems.append(f"{label}: run {run_id} durable evidence file missing")
            continue
        observed = sha256_file(evidence_path)
        if observed != raw_digest:
            problems.append(f"{label}: run {run_id} evidence sha256 {observed} != manifest {raw_digest}")
            continue

        evidence = _load_json(evidence_path, problems, f"{label}/run-{run_id}")
        if evidence is None:
            continue
        if str(evidence.get("run_id")) != run_id:
            problems.append(f"{label}: run {run_id} evidence run_id mismatch")
        if evidence.get("scenario_hashes") != scenario_hashes:
            problems.append(f"{label}: run {run_id} evidence scenario_hashes differ from manifest")
        if evidence.get("acceptance") != run.get("acceptance"):
            problems.append(f"{label}: run {run_id} acceptance differs from manifest")
        cleanup = evidence.get("cleanup")
        if not isinstance(cleanup, list) or not cleanup or any(x.get("state") != "closed" for x in cleanup if isinstance(x, dict)):
            problems.append(f"{label}: run {run_id} cleanup must show all created objects closed")
        claimed_issues = run.get("issues")
        observed_issues = sorted(x.get("number") for x in cleanup if isinstance(x, dict) and isinstance(x.get("number"), int)) if isinstance(cleanup, list) else []
        if not isinstance(claimed_issues, list) or sorted(claimed_issues) != observed_issues:
            problems.append(f"{label}: run {run_id} issue list differs from cleanup evidence")

        rows = evidence.get("rows")
        by_key: dict[tuple[str, str], dict] = {}
        if not isinstance(rows, list):
            problems.append(f"{label}: run {run_id} rows must be a list")
            continue
        for row in rows:
            if isinstance(row, dict) and isinstance(row.get("scenario"), str) and isinstance(row.get("system"), str):
                by_key[(row["scenario"], row["system"])] = row
        for scenario, expected_row in matrix_by_scenario.items():
            for system in ("unsafe", "guarded"):
                row = by_key.get((scenario, system))
                if row is None:
                    problems.append(f"{label}: run {run_id} missing row {scenario}/{system}")
                    continue
                observed_label = "PASS" if row.get("pass") is True else "FAIL"
                if observed_label != expected_row.get(system):
                    problems.append(f"{label}: run {run_id} {scenario}/{system}={observed_label}, expected {expected_row.get(system)}")

    readme_text = readme.read_text(encoding="utf-8")
    if "## Independent rerun" not in readme_text:
        problems.append(f"{label}: README must contain an Independent rerun section")
    if runner_path and runner_path not in readme_text:
        problems.append(f"{label}: README must name the exact runner path")
    if workflow_path and workflow_path not in readme_text:
        problems.append(f"{label}: README must name the exact workflow path")

    return problems


def validate_results_dir(root: Path, results_dir: Path | None = None) -> tuple[bool, str]:
    """Validate every published bundle in results/. Empty results/ is valid before first publication."""
    results = results_dir or (root / "results")
    if not results.exists() or not results.is_dir():
        return False, "results/ directory missing"

    unexpected_files = sorted(p.name for p in results.iterdir() if p.is_file() and p.name != "README.md")
    if unexpected_files:
        return False, f"unexpected files directly in results/: {unexpected_files}"

    bundles = sorted(p for p in results.iterdir() if p.is_dir())
    if not bundles:
        return True, "no published result bundles; results/ contains README.md only"

    problems: list[str] = []
    for bundle in bundles:
        problems.extend(_validate_bundle(root, bundle))
    if problems:
        return False, "; ".join(problems)
    return True, f"{len(bundles)} published result bundle(s) validated with durable evidence and provenance"
