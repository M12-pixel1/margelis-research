from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
GITHUB_WORKFLOW = ROOT / ".github" / "workflows" / "benchmark-live-github.yml"
GITHUB_RUNNER = Path(__file__).with_name("github_issues_runner.py")
STRIPE_WORKFLOW = ROOT / ".github" / "workflows" / "benchmark-live-stripe.yml"
STRIPE_RUNNER = Path(__file__).with_name("stripe_payment_runner.py")


def _output_assignment_source(source: str) -> str | None:
    tree = ast.parse(source)
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if any(isinstance(target, ast.Name) and target.id == "OUTPUT" for target in targets):
            return ast.get_source_segment(source, node)
    return None


def _manual_only(workflow: str, label: str, failures: list[str]) -> None:
    """The only trigger may be workflow_dispatch, in any YAML spelling (mapping, inline mapping or list)."""
    import yaml
    doc = yaml.safe_load(workflow) or {}
    on = doc.get("on", doc.get(True))  # PyYAML reads a bare `on` key as boolean True
    if isinstance(on, str):
        triggers = {on}
    elif isinstance(on, list):
        triggers = set(on)
    elif isinstance(on, dict):
        triggers = set(on)
    else:
        triggers = set()
    if "workflow_dispatch" not in triggers:
        failures.append(f"{label} workflow must require workflow_dispatch")
    for extra in sorted(triggers - {"workflow_dispatch"}):
        failures.append(f"{label} workflow must not run on {extra}")


def main() -> int:
    github_workflow = GITHUB_WORKFLOW.read_text()
    github_runner = GITHUB_RUNNER.read_text()
    stripe_workflow = STRIPE_WORKFLOW.read_text()
    stripe_runner = STRIPE_RUNNER.read_text()
    failures: list[str] = []

    # Existing GitHub P0-3 live boundary.
    _manual_only(github_workflow, "GitHub live", failures)
    if "inputs.confirm == 'RUN_LIVE_GITHUB_P0_3'" not in github_workflow:
        failures.append("GitHub live workflow must retain explicit human confirmation gate")
    if "contents: read" not in github_workflow or "issues: write" not in github_workflow:
        failures.append("GitHub live permissions must stay contents:read + issues:write")
    if "contents: write" in github_workflow:
        failures.append("GitHub live workflow must not have contents:write")
    if "finally:" not in github_runner or 'state="closed"' not in github_runner:
        failures.append("GitHub live runner must keep finally-based issue cleanup")
    if "LIVE_EXTERNAL_SYSTEM_CANDIDATE_NOT_PUBLISHED" not in github_runner:
        failures.append("GitHub live output must remain candidate/not-published")

    github_output = _output_assignment_source(github_runner)
    if github_output is None:
        failures.append("GitHub live runner must define an explicit OUTPUT evidence target")
    else:
        if "VDB_EVIDENCE_PATH" not in github_output:
            failures.append("GitHub live evidence target must remain configurable")
        if "vdb-live-github-evidence.json" not in github_output:
            failures.append("GitHub live evidence default must remain dedicated")
        if "results" in github_output.lower():
            failures.append("GitHub live evidence OUTPUT must not target benchmark results")

    # Stripe P0-4A financial-provider boundary.
    _manual_only(stripe_workflow, "Stripe live", failures)
    if "inputs.confirm == 'RUN_STRIPE_P0_4A'" not in stripe_workflow:
        failures.append("Stripe live workflow must retain explicit human confirmation gate")
    if "contents: read" not in stripe_workflow or "contents: write" in stripe_workflow:
        failures.append("Stripe live workflow permissions must stay contents:read only")
    if "STRIPE_VDB_SANDBOX_SECRET_KEY" not in stripe_workflow:
        failures.append("Stripe live workflow must use the dedicated sandbox secret")
    if "sk_live_" in stripe_workflow or "rk_live_" in stripe_workflow:
        failures.append("Stripe live workflow must never embed a live-key marker")
    if "RUN_STRIPE_P0_4A" not in stripe_workflow:
        failures.append("Stripe live workflow confirmation token missing")

    # Parsing is also a syntax gate for the live runner.
    stripe_tree = ast.parse(stripe_runner)
    del stripe_tree
    for marker in (
        "REFUSED: live Stripe API key detected",
        "livemode",
        "pm_card_visa",
        "LIVE_EXTERNAL_SYSTEM_CANDIDATE_NOT_PUBLISHED",
        "toctou_authority_revocation",
    ):
        if marker not in stripe_runner:
            failures.append(f"Stripe live runner missing required safety/evidence marker: {marker}")

    stripe_output = _output_assignment_source(stripe_runner)
    if stripe_output is None:
        failures.append("Stripe live runner must define an explicit OUTPUT evidence target")
    else:
        if "VDB_EVIDENCE_PATH" not in stripe_output:
            failures.append("Stripe live evidence target must remain configurable")
        if "vdb-live-stripe-evidence.json" not in stripe_output:
            failures.append("Stripe live evidence default must remain dedicated")
        if "results" in stripe_output.lower():
            failures.append("Stripe live evidence OUTPUT must not target benchmark results")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1

    print("PASS: live GitHub and Stripe benchmark workflows remain manual-only and bounded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
