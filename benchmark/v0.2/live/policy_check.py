from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "benchmark-live-github.yml"
RUNNER = Path(__file__).with_name("github_issues_runner.py")


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
    if "benchmark/v0.2/results" in runner:
        failures.append("live runner must not write benchmark results directly")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print("PASS: live GitHub benchmark workflow remains manual-only and bounded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
