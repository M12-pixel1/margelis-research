from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "benchmark-live-github.yml"
RUNNER = Path(__file__).with_name("github_issues_runner.py")


def _output_assignment_source(source: str) -> str | None:
    """Return the source for the module-level OUTPUT assignment, if present."""
    tree = ast.parse(source)
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if any(isinstance(target, ast.Name) and target.id == "OUTPUT" for target in targets):
            return ast.get_source_segment(source, node)
    return None


def main() -> int:
    workflow = WORKFLOW.read_text()
    runner = RUNNER.read_text()
    failures: list[str] = []

    if "workflow_dispatch:" not in workflow:
        failures.append("live workflow must require workflow_dispatch")
    if re.search(r"(?m)^\s*push:\s*$", workflow):
        failures.append("live workflow must not run on push")
    if re.search(r"(?m)^\s*pull_request:\s*$", workflow):
        failures.append("live workflow must not run on pull_request")
    if "inputs.confirm == 'RUN_LIVE_GITHUB_P0_3'" not in workflow:
        failures.append("live workflow must retain explicit human confirmation gate")
    if "contents: read" not in workflow or "issues: write" not in workflow:
        failures.append("live workflow permissions must stay contents:read + issues:write")
    if "contents: write" in workflow:
        failures.append("live workflow must not have contents:write")
    if "finally:" not in runner or "state=\"closed\"" not in runner:
        failures.append("live runner must keep finally-based issue cleanup")
    if "LIVE_EXTERNAL_SYSTEM_CANDIDATE_NOT_PUBLISHED" not in runner:
        failures.append("live output must remain candidate/not-published")

    output_assignment = _output_assignment_source(runner)
    if output_assignment is None:
        failures.append("live runner must define an explicit OUTPUT evidence target")
    else:
        if "VDB_EVIDENCE_PATH" not in output_assignment:
            failures.append("live evidence target must remain configurable via VDB_EVIDENCE_PATH")
        if "vdb-live-github-evidence.json" not in output_assignment:
            failures.append("live evidence default must remain the dedicated evidence JSON file")
        if "results" in output_assignment.lower():
            failures.append("live evidence OUTPUT must not target benchmark results")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print("PASS: live GitHub benchmark workflow remains manual-only and bounded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
