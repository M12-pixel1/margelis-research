#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mrpub.benchmark_results import validate_results_dir  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "benchmark" / "v0.2"
CANDIDATE = BENCHMARK / "candidates" / "github-p0-3-repeatability"


def materialize_published_bundle(base: Path) -> Path:
    results = base / "results"
    results.mkdir(parents=True)
    (results / "README.md").write_text("# Test results\n", encoding="utf-8")
    bundle = results / "github-p0-3-repeatability-2026-09-17"
    shutil.copytree(CANDIDATE, bundle)
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["status"] = "PUBLISHED_RESULT"
    manifest["result_id"] = bundle.name
    manifest.pop("candidate_id", None)
    manifest["publication_readiness"] = {"ready": True, "blockers": []}
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return results


def require(condition: bool, label: str, detail: str = "") -> None:
    if not condition:
        raise AssertionError(f"{label}: {detail}")
    print(f"PASS {label}" + (f": {detail}" if detail else ""))


def main() -> int:
    ok, detail = validate_results_dir(BENCHMARK)
    require(ok, "empty-current-results", detail)

    with tempfile.TemporaryDirectory() as tmp:
        results = materialize_published_bundle(Path(tmp))
        ok, detail = validate_results_dir(BENCHMARK, results)
        require(ok, "complete-bundle-accepted", detail)

    with tempfile.TemporaryDirectory() as tmp:
        results = materialize_published_bundle(Path(tmp))
        evidence = results / "github-p0-3-repeatability-2026-09-17" / "evidence" / "run-35216991313.json"
        evidence.write_bytes(evidence.read_bytes() + b"\n")
        ok, detail = validate_results_dir(BENCHMARK, results)
        require(not ok and "evidence sha256" in detail, "tampered-evidence-rejected", detail)

    with tempfile.TemporaryDirectory() as tmp:
        results = materialize_published_bundle(Path(tmp))
        manifest_path = results / "github-p0-3-repeatability-2026-09-17" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["scenario_hashes"]["replay"] = "sha256:" + "0" * 64
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        ok, detail = validate_results_dir(BENCHMARK, results)
        require(not ok and "scenario hash mismatch" in detail, "scenario-hash-drift-rejected", detail)

    with tempfile.TemporaryDirectory() as tmp:
        results = materialize_published_bundle(Path(tmp))
        missing = results / "github-p0-3-repeatability-2026-09-17" / "evidence" / "run-35231849182.json"
        missing.unlink()
        ok, detail = validate_results_dir(BENCHMARK, results)
        require(not ok and "durable evidence file missing" in detail, "missing-evidence-rejected", detail)

    with tempfile.TemporaryDirectory() as tmp:
        results = materialize_published_bundle(Path(tmp))
        manifest_path = results / "github-p0-3-repeatability-2026-09-17" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["publication_readiness"] = {"ready": False, "blockers": ["human gate not passed"]}
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        ok, detail = validate_results_dir(BENCHMARK, results)
        require(not ok and "publication_readiness" in detail, "unready-bundle-rejected", detail)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
