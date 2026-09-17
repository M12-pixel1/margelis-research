"""Deterministic positive/negative self-tests for benchmark result-bundle validation."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from .benchmark_results import validate_results_dir
from .common import git, sha256_file, write_json, write_text

SCENARIOS = ("expired_mandate", "replay", "false_done")


def _make_bundle(root: Path, results: Path) -> Path:
    results.mkdir(parents=True, exist_ok=True)
    write_text(results / "README.md", "# Self-test results\n")
    bundle = results / "selftest-result"
    evidence_dir = bundle / "evidence"
    evidence_dir.mkdir(parents=True)

    commit = git("rev-parse", "HEAD")
    runner_path = "benchmark/v0.2/live/github_issues_runner.py"
    workflow_path = ".github/workflows/benchmark-live-github.yml"
    runner_blob = git("rev-parse", f"{commit}:{runner_path}")
    scenario_hashes = {
        scenario: "sha256:" + sha256_file(root / "scenarios" / f"{scenario}.yaml")
        for scenario in SCENARIOS
    }
    acceptance = {
        "unsafe_all_fail": True,
        "guarded_all_pass": True,
        "all_created_issues_closed": True,
    }
    matrix = [
        {"scenario": scenario, "unsafe": "FAIL", "guarded": "PASS", "runs_agree": True}
        for scenario in SCENARIOS
    ]

    runs = []
    for idx, run_id in enumerate((900000001, 900000002), start=1):
        issues = [idx * 10 + n for n in range(1, 6)]
        cleanup = [{"number": n, "state": "closed"} for n in issues]
        rows = []
        for scenario in SCENARIOS:
            rows.append({"scenario": scenario, "system": "unsafe", "pass": False})
            rows.append({"scenario": scenario, "system": "guarded", "pass": True})
        evidence = {
            "run_id": str(run_id),
            "scenario_hashes": scenario_hashes,
            "acceptance": acceptance,
            "cleanup": cleanup,
            "rows": rows,
        }
        evidence_path = evidence_dir / f"run-{run_id}.json"
        write_json(evidence_path, evidence)
        runs.append({
            "run_id": run_id,
            "acceptance": acceptance,
            "issues": issues,
            "raw_evidence_json_sha256": sha256_file(evidence_path),
        })

    manifest = {
        "status": "PUBLISHED_RESULT",
        "benchmark": "Verified Delegation Benchmark v0.2",
        "result_id": bundle.name,
        "source": {
            "main_commit": commit,
            "runner_path": runner_path,
            "runner_blob_sha": runner_blob,
            "workflow_path": workflow_path,
        },
        "scenario_hashes": scenario_hashes,
        "runs": runs,
        "repeatability": {
            "scenario_hashes_identical": True,
            "acceptance_matrix_identical": True,
            "external_state_pattern_identical": True,
        },
        "result_matrix": matrix,
        "publication_readiness": {"ready": True, "blockers": []},
        "limitations": ["Synthetic self-test bundle only."],
    }
    write_json(bundle / "manifest.json", manifest)
    write_text(
        bundle / "README.md",
        "# Self-test result\n\n## Independent rerun\n\n"
        f"Runner: `{runner_path}`\n\nWorkflow: `{workflow_path}`\n",
    )
    return bundle


def run_selftest(root: Path) -> tuple[bool, str]:
    checks: list[tuple[bool, str]] = []

    with tempfile.TemporaryDirectory() as tmp:
        results = Path(tmp) / "results"
        bundle = _make_bundle(root, results)
        ok, detail = validate_results_dir(root, results)
        checks.append((ok, f"complete bundle accepted ({detail})"))

        evidence = bundle / "evidence" / "run-900000001.json"
        original_evidence = evidence.read_bytes()
        evidence.write_bytes(original_evidence + b"\n")
        ok, detail = validate_results_dir(root, results)
        checks.append((not ok and "evidence sha256" in detail, "tampered evidence rejected"))
        evidence.write_bytes(original_evidence)

        manifest_path = bundle / "manifest.json"
        original_manifest = manifest_path.read_text(encoding="utf-8")
        manifest = json.loads(original_manifest)
        manifest["scenario_hashes"]["replay"] = "sha256:" + "0" * 64
        write_json(manifest_path, manifest)
        ok, detail = validate_results_dir(root, results)
        checks.append((not ok and "scenario hash mismatch" in detail, "scenario hash drift rejected"))
        manifest_path.write_text(original_manifest, encoding="utf-8", newline="\n")

        missing = bundle / "evidence" / "run-900000002.json"
        missing_bytes = missing.read_bytes()
        missing.unlink()
        ok, detail = validate_results_dir(root, results)
        checks.append((not ok and "durable evidence file missing" in detail, "missing evidence rejected"))
        missing.write_bytes(missing_bytes)

        manifest = json.loads(original_manifest)
        manifest["publication_readiness"] = {"ready": False, "blockers": ["human gate"]}
        write_json(manifest_path, manifest)
        ok, detail = validate_results_dir(root, results)
        checks.append((not ok and "publication_readiness" in detail, "unready bundle rejected"))

    failed = [label for passed, label in checks if not passed]
    if failed:
        return False, "self-test failures: " + "; ".join(failed)
    return True, "; ".join(label for _, label in checks)
