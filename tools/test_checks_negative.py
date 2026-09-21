"""Paired negative tests: every guard in `publish.py check` must bite when its failure is injected.

Each case copies the repository (with .git) into a temporary directory, injects one defect and
runs the named check there. The check must PASS on the unmutated copy and FAIL, with the
expected explanation, on the mutated one; a guard that cannot fail, or that fails for another
reason, is not a guard. Runs offline.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAKE_TOKEN = "gh" + "p_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"  # synthetic, not a credential
NOTE_MD = "research/001/Margelis_Research_Note_001.md"
BUNDLE = "benchmark/v0.2/results/github-p0-3-repeatability-2026-09-17"
RUNNER = "benchmark/v0.2/live/github_issues_runner.py"


def append(rel, text):
    def f(root):
        p = root / rel
        p.write_text(p.read_text(encoding="utf-8") + text, encoding="utf-8", newline="\n")
    return f


def replace(rel, old, new):
    def f(root):
        p = root / rel
        s = p.read_text(encoding="utf-8")
        assert old in s, f"{rel}: {old!r} not found"
        p.write_text(s.replace(old, new, 1), encoding="utf-8", newline="\n")
    return f


def flip_last_bytes(rel):
    def f(root):
        p = root / rel
        b = bytearray(p.read_bytes())
        b[-10] ^= 1
        p.write_bytes(bytes(b))
    return f


def write(rel, text):
    def f(root):
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")
    return f


def edit_json(rel, mutate):
    def f(root):
        p = root / rel
        data = json.loads(p.read_text(encoding="utf-8"))
        mutate(data)
        p.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")
    return f


def different_runner_at_head(root):
    """Commit a modified runner in the copy and point run 1's head_sha at that commit."""
    p = root / RUNNER
    p.write_text(p.read_text(encoding="utf-8") + "\n# changed for the negative test\n", encoding="utf-8", newline="\n")
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@localhost"]
    subprocess.run(git + ["commit", "-qam", "negative test: different runner"], cwd=root, check=True,
                   capture_output=True)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True,
                          text=True).stdout.strip()
    edit_json(f"{BUNDLE}/manifest.json", lambda d: d["runs"][0].__setitem__("head_sha", head))(root)


def evidence_item_injected(root):
    """Add an evidence item without updating the receipt, then re-sync the file digest in the manifest
    so that only the receipt/evidence guard can catch it."""
    import hashlib
    ev = root / f"{BUNDLE}/evidence/run-35216991313.json"
    edit_json(f"{BUNDLE}/evidence/run-35216991313.json", lambda d: d["rows"][0]["evidence"].append({"injected": True}))(root)
    digest = hashlib.sha256(ev.read_bytes()).hexdigest()
    edit_json(f"{BUNDLE}/manifest.json", lambda d: d["runs"][0].__setitem__("raw_evidence_json_sha256", digest))(root)


CASES = [
    ("novelty claim in the note", append(NOTE_MD, "\nThis is a world-first framework.\n"),
     "note001.published_claims", "unsupported claim language"),
    ("locked limitation removed", replace(NOTE_MD, "- Metric thresholds are not industry standards.\n", ""),
     "note001.locked_statements", "missing"),
    ("PDF byte flipped", flip_last_bytes("research/001/Margelis_Research_Note_001.pdf"),
     "note001.sha256sums", "digest mismatch"),
    ("credential in README", append("README.md", f"\ntoken: {FAKE_TOKEN}\n"), "repo.secret_scan", "github-token"),
    ("license granted without spdx", replace("research/001/note.yaml", "  spdx: CC-BY-4.0", "  spdx: null"),
     "note001.input_schema", "spdx"),
    ("stray file directly in results/", write("benchmark/v0.2/results/run-001.json", "{}"),
     "benchmark.result_bundles", "unexpected files directly in results/"),
    ("tampered evidence in a published bundle", append(f"{BUNDLE}/evidence/run-35216991313.json", "\n"),
     "benchmark.result_bundles", "evidence sha256"),
    ("bundle scenario hash drift", edit_json(f"{BUNDLE}/manifest.json",
                                             lambda d: d["scenario_hashes"].__setitem__("replay", "sha256:" + "0" * 64)),
     "benchmark.result_bundles", "scenario hash mismatch"),
    ("bundle run without head_sha", edit_json(f"{BUNDLE}/manifest.json", lambda d: d["runs"][0].pop("head_sha")),
     "benchmark.result_bundles", "head_sha must be"),
    ("bundle run at a commit without the runner", edit_json(
        f"{BUNDLE}/manifest.json", lambda d: d["runs"][0].__setitem__("head_sha", "22ffe19925cd8e240590c22e81ce742864262310")),
     "benchmark.result_bundles", "does not contain"),
    ("bundle run at a commit with a different runner", different_runner_at_head,
     "benchmark.result_bundles", "executed a different runner"),
    ("receipt evidence hashes do not match the evidence", evidence_item_injected,
     "benchmark.result_bundles", "evidence_hashes do not match"),
    ("benchmark docs deny a published result", replace("benchmark/v0.2/README.md", "Status:", "Status: results/ stays empty.\n\nStatus:"),
     "benchmark.docs_consistency", "results/ stays empty"),
    ("stale version in repository README", replace("README.md", "| 1.1 |", "| 1.0 |"), "repo.docs_current", "out of date"),
    ("README calls a granted license pending", replace("README.md", "## License\n", "## License\n\nPending.\n"),
     "note001.license_consistency", "README license section"),
    ("author misspelled on the page", replace("site/research/001/index.html", "<strong>Tomas Margelis</strong>", "<strong>Thomas Margelis</strong>"),
     "note001.name_spelling", "Thomas Margelis"),
    ("canonical URL drift", replace("site/research/001/index.html", 'rel="canonical" href="https://rupestelisholding.com/research/001/"',
                                    'rel="canonical" href="https://example.com/x/"'), "note001.site_page", "canonical"),
    ("broken internal link", replace("site/research/index.html", 'href="001/"', 'href="002/"'), "repo.internal_links", "002/"),
    ("unlisted external link", append(NOTE_MD, "\nSee <https://example.com/unverified>.\n"),
     "note001.references_cited", "not in references.json"),
    ("lock file out of step with requirements", replace("tools/requirements.txt", "reportlab==4.5.0", "reportlab==4.4.0"),
     "repo.dependency_lock", "requirements 4.4.0"),
    ("unpinned action in a workflow", replace(".github/workflows/pages.yml", "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
                                              "actions/checkout@v7"), "repo.workflow_pins", "not pinned"),
]


def fresh_copy(tmp: str) -> Path:
    root = Path(tmp) / "repo"
    # .git is copied so that provenance checks (tags, blobs, released digests) work in the copy
    shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns("__pycache__", ".cache", ".venv"))
    return root


def run_check(root: Path, check_id: str) -> tuple[str, int]:
    out = subprocess.run([sys.executable, "tools/publish.py", "check", "001", "--only", check_id],
                         cwd=root, capture_output=True, text=True, encoding="utf-8")
    line = next((l for l in out.stdout.splitlines() if f" {check_id} " in f" {l} "), "")
    return line or out.stderr.strip()[-160:], out.returncode


def main() -> int:
    ok_all = True
    with tempfile.TemporaryDirectory() as tmp:
        clean = fresh_copy(tmp)
        for check_id in sorted({c[2] for c in CASES}):
            line, rc = run_check(clean, check_id)
            good = line.startswith("PASS") and rc == 0
            ok_all &= good
            print(f"{'BASELINE PASS' if good else 'BASELINE BROKEN'}  {check_id:34} -> {line[:90]}")
    for label, mutate, check_id, expected in CASES:
        with tempfile.TemporaryDirectory() as tmp:
            root = fresh_copy(tmp)
            mutate(root)
            line, rc = run_check(root, check_id)
        caught = line.startswith("FAIL") and rc == 1 and expected in line
        ok_all &= caught
        print(f"{'CAUGHT' if caught else 'MISSED'}  {label:48} -> {line[:110]}")
    print(f"\n{'all' if ok_all else 'NOT all'} {len(CASES)} injected defects caught with the expected explanation")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
