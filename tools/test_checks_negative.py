"""Paired negative tests: every guard in `publish.py check` must bite when its failure is injected.

Each case copies the repository into a temporary directory, injects one defect and runs the
named check there. A guard that cannot fail is not a guard, so a case that stays PASS fails
this test. Runs offline.
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


CASES = [
    ("novelty claim in the note", append(NOTE_MD, "\nThis is a world-first framework.\n"), "note001.published_claims"),
    ("locked limitation removed", replace(NOTE_MD, "- Metric thresholds are not industry standards.\n", ""), "note001.locked_statements"),
    ("PDF byte flipped", flip_last_bytes("research/001/Margelis_Research_Note_001.pdf"), "note001.sha256sums"),
    ("credential in README", append("README.md", f"\ntoken: {FAKE_TOKEN}\n"), "repo.secret_scan"),
    ("license granted without spdx", replace("research/001/note.yaml", "  spdx: CC-BY-4.0", "  spdx: null"), "note001.input_schema"),
    ("stray file directly in results/", write("benchmark/v0.2/results/run-001.json", "{}"), "benchmark.result_bundles"),
    ("tampered evidence in a published bundle", append(f"{BUNDLE}/evidence/run-35216991313.json", "\n"), "benchmark.result_bundles"),
    ("bundle scenario hash drift", edit_json(f"{BUNDLE}/manifest.json",
                                             lambda d: d["scenario_hashes"].__setitem__("replay", "sha256:" + "0" * 64)),
     "benchmark.result_bundles"),
    ("bundle run claims a head commit with a different runner", edit_json(f"{BUNDLE}/manifest.json",
                                                                          lambda d: d["runs"][0].__setitem__("head_sha", "22ffe19925cd8e240590c22e81ce742864262310")),
     "benchmark.result_bundles"),
    ("benchmark docs deny a published result", replace("benchmark/v0.2/README.md", "Status:", "Status: results/ stays empty.\n\nStatus:"),
     "benchmark.docs_consistency"),
    ("stale version in repository README", replace("README.md", "| 1.1 |", "| 1.0 |"), "repo.docs_current"),
    ("README calls a granted license pending", replace("README.md", "## License\n", "## License\n\nPending.\n"), "note001.license_consistency"),
    ("author misspelled on the page", replace("site/research/001/index.html", "<strong>Tomas Margelis</strong>", "<strong>Thomas Margelis</strong>"),
     "note001.name_spelling"),
    ("canonical URL drift", replace("site/research/001/index.html", 'rel="canonical" href="https://rupestelisholding.com/research/001/"',
                                    'rel="canonical" href="https://example.com/x/"'), "note001.site_page"),
    ("broken internal link", replace("site/research/index.html", 'href="001/"', 'href="002/"'), "repo.internal_links"),
    ("unlisted external link", append(NOTE_MD, "\nSee <https://example.com/unverified>.\n"), "note001.references_cited"),
    ("lock file out of step with requirements", replace("tools/requirements.txt", "reportlab==4.5.0", "reportlab==4.4.0"), "repo.dependency_lock"),
]


def run_case(label, mutate, check_id) -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "repo"
        # .git is copied so that provenance checks (tags, blobs, released digests) work in the copy
        shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns("__pycache__", ".cache", ".venv"))
        mutate(root)
        out = subprocess.run([sys.executable, "tools/publish.py", "check", "001", "--only", check_id],
                             cwd=root, capture_output=True, text=True, encoding="utf-8")
        line = next((l for l in out.stdout.splitlines() if f" {check_id} " in f" {l} "), "")
        caught = line.startswith("FAIL") and out.returncode == 1
        print(f"{'CAUGHT' if caught else 'MISSED'}  {label:44} -> {line[:110] or out.stderr.strip()[-110:]}")
        return caught


def main() -> int:
    results = [run_case(*case) for case in CASES]
    print(f"\n{sum(results)}/{len(results)} injected defects caught")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
