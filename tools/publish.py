#!/usr/bin/env python3
"""Margelis Research publication pipeline.

Reversible steps
  new NNN --title T --subtitle S   scaffold research/NNN/ for a new note
  check [NNN ...] [--online]       validate inputs, built artifacts, benchmark, links, secrets
  build NNN                        PDF -> metadata.json -> SHA256SUMS -> web pages -> CITATION.cff
  verify NNN [--rebuild] [--online]  check + byte-for-byte PDF rebuild
  all NNN                          build + check --online + verify --rebuild (stops before publication)
  receipt NNN                      probe every publication location, write publication-receipt.json
  check-benchmark                  validate benchmark scenarios and receipt schema

Publication steps (outward-facing)
  release NNN [--dry-run] [--update-notes]   GitHub release: draft -> assets -> publish -> verify
  zenodo NNN [--sandbox] [--dry-run]         create/verify a private Zenodo draft, reserve the DOI
  zenodo NNN --publish --confirm-doi DOI     publish the draft (irreversible; needs a granted license)

Human decision
  grant-license NNN --spdx CC-BY-4.0 --by NAME --on YYYY-MM-DD   record an explicit license grant

Exit codes: 0 ok, 1 failed check or error, 3 blocked on a missing credential.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mrpub import build, checks, receipt, release, zenodo  # noqa: E402
from mrpub.common import RESEARCH, PipelineError, all_notes, load_note, write_text  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def show(results: list[checks.Result]) -> bool:
    width = max(len(r.id) for r in results)
    for r in results:
        print(f"{r.status:<5} {r.id:<{width}}  {r.detail}")
    counts = {s: sum(1 for r in results if r.status == s) for s in ("PASS", "FAIL", "WARN", "SKIP")}
    print(f"\n{counts['PASS']} passed, {counts['FAIL']} failed, {counts['WARN']} warnings, {counts['SKIP']} skipped")
    return counts["FAIL"] == 0


def run_checks(numbers: list[str], online: bool, rebuild: bool = False) -> list[checks.Result]:
    results = []
    for num in numbers:
        note = load_note(num)
        built = note.metadata_path.exists() and note.pdf_path.exists() and note.sums_path.exists()
        results += checks.NoteChecks(note, online=online).run(built=built)
        if not built:
            results.append(checks.Result(f"note{note.number}.built", "FAIL", "not built yet: run `build`"))
        elif rebuild:
            results.append(checks.check_reproducible(note))
    results += checks.check_benchmark()
    results.append(checks.check_internal_links())
    results.append(checks.check_secrets())
    return results


def cmd_new(args) -> int:
    num = f"{int(args.number):03d}"
    d = RESEARCH / num
    if d.exists():
        raise PipelineError(f"{d} already exists")
    template = (RESEARCH / "001" / "note.yaml").read_text(encoding="utf-8")
    head, _, _ = template.partition("abstract:")
    head = (head.replace('number: "001"', f'number: "{num}"')
                .replace('version: "1.0"', 'version: "1.0"')
                .replace("title: From Mandate to Verified Outcome", f"title: {args.title}")
                .replace("subtitle: An Evaluation Framework for Autonomous Agent Execution",
                         f"subtitle: {args.subtitle}")
                .replace("Research Note 001", f"Research Note {num}")
                .replace("research/001/", f"research/{num}/")
                .replace("build 001", f"build {num}"))
    write_text(d / "note.yaml", head + """abstract: >-
  TODO: one-paragraph abstract (at least 40 characters).

keywords:
  - TODO

web_keywords:
  - TODO

license:
  status: pending
  spdx: null
  proposed: CC-BY-4.0
  scope: >-
    Research Note text only (the Markdown and PDF files of this note).
  authorized_by: null
  authorized_on: null

locked_statements:
  What remains unproven: []

version_history:
  - version: "1.0"
    date: "YYYY-MM-DD"
    summary: Initial publication.
""")
    write_text(d / f"Margelis_Research_Note_{num}.md", f"""MARGELIS RESEARCH

# {args.title}

**{args.subtitle}**

Author Name\\
Rūpestėlis Holding\\
Research Note {num} · v1.0 · D Month YYYY

---

**Executive thesis.** TODO

## 1. TODO

TODO

## 2. Prior art

1. TODO: verified reference with URL.

## 3. What remains unproven

- TODO

---

## About this document

**Series.** Margelis Research · Research Note {num} · Version 1.0 · D Month YYYY.
""")
    write_text(d / "references.json", '{\n  "note": "%s",\n  "checked_on": null,\n  "method": "TODO",\n  "references": []\n}\n' % num)
    write_text(d / "README.md", f"# Margelis Research Note {num}\n\nDraft. Run `python tools/publish.py check {num}`.\n")
    print(f"Scaffolded {d}. Edit note.yaml, the Markdown file and references.json, then run:\n"
          f"  python tools/publish.py all {num}")
    return 0


def cmd_grant_license(args) -> int:
    """Record an explicit license grant in note.yaml (the only place a license can come from)."""
    import datetime as dt
    import re
    note = load_note(args.number)
    if note.license_granted:
        raise PipelineError(f"note {note.number} already records a granted license ({note.license['spdx']})")
    dt.date.fromisoformat(args.on)
    path = note.dir / "note.yaml"
    text = path.read_text(encoding="utf-8")
    for pattern, value in ((r"^  status: pending$", "  status: granted"),
                           (r"^  spdx: null$", f"  spdx: {args.spdx}"),
                           (r"^  authorized_by: null$", f'  authorized_by: "{args.by}"'),
                           (r"^  authorized_on: null$", f'  authorized_on: "{args.on}"')):
        text, count = re.subn(pattern, value, text, count=1, flags=re.M)
        if count != 1:
            raise PipelineError(f"could not find '{pattern}' in {path}")
    write_text(path, text)
    print(f"Recorded: {args.spdx} granted by {args.by} on {args.on} for note {note.number}.\n"
          f"Next: python tools/publish.py build {note.number} && python tools/publish.py check {note.number} --online,\n"
          f"      commit + push, then python tools/publish.py release {note.number} --update-notes")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("new"); s.add_argument("number"); s.add_argument("--title", required=True)
    s.add_argument("--subtitle", required=True)
    s = sub.add_parser("check"); s.add_argument("numbers", nargs="*"); s.add_argument("--online", action="store_true")
    s = sub.add_parser("build"); s.add_argument("numbers", nargs="+")
    s = sub.add_parser("verify"); s.add_argument("numbers", nargs="*"); s.add_argument("--rebuild", action="store_true")
    s.add_argument("--online", action="store_true")
    s = sub.add_parser("all"); s.add_argument("number")
    s = sub.add_parser("receipt"); s.add_argument("number"); s.add_argument("--offline-checks", action="store_true")
    sub.add_parser("check-benchmark")
    s = sub.add_parser("release"); s.add_argument("number"); s.add_argument("--dry-run", action="store_true")
    s.add_argument("--update-notes", action="store_true")
    s = sub.add_parser("zenodo"); s.add_argument("number"); s.add_argument("--sandbox", action="store_true")
    s.add_argument("--dry-run", action="store_true"); s.add_argument("--publish", action="store_true")
    s.add_argument("--confirm-doi")
    s = sub.add_parser("grant-license"); s.add_argument("number"); s.add_argument("--spdx", required=True)
    s.add_argument("--by", required=True); s.add_argument("--on", required=True, help="YYYY-MM-DD")
    args = p.parse_args(argv)

    try:
        if args.cmd == "new":
            return cmd_new(args)
        if args.cmd == "grant-license":
            return cmd_grant_license(args)
        if args.cmd == "check":
            return 0 if show(run_checks(args.numbers or all_notes(), args.online)) else 1
        if args.cmd == "check-benchmark":
            return 0 if show(checks.check_benchmark()) else 1
        if args.cmd == "build":
            for num in args.numbers:
                info = build.build_note(load_note(num))
                print(f"built note {info['note']} v{info['version']}: {info['pages']} pages")
                for name, digest in info["sha256"].items():
                    print(f"  {digest}  {name}")
            for path in build.build_site_and_citation():
                print(f"  wrote {path.relative_to(RESEARCH.parent).as_posix()}")
            return 0
        if args.cmd == "verify":
            return 0 if show(run_checks(args.numbers or all_notes(), args.online, rebuild=args.rebuild)) else 1
        if args.cmd == "all":
            note = load_note(args.number)
            build.build_note(note)
            build.build_site_and_citation()
            ok = show(run_checks([note.number], online=True, rebuild=True))
            print("\nStopped before publication. Next (outward-facing) steps:\n"
                  f"  git add -A && git commit && git push\n"
                  f"  python tools/publish.py release {note.number}\n"
                  f"  python tools/publish.py zenodo {note.number}\n"
                  f"  python tools/publish.py receipt {note.number}")
            return 0 if ok else 1
        if args.cmd == "receipt":
            note = load_note(args.number)
            results = run_checks([note.number], online=not args.offline_checks, rebuild=True)
            data = receipt.write(note, results)
            print(f"status={data['status']} commit={data['commit_sha']} doi={data['doi']}")
            for b in data["blockers"]:
                print(f"  BLOCKED {b['item']}: {b['state']} - {b['cause']}")
            print(f"wrote {note.receipt_path.relative_to(RESEARCH.parent).as_posix()}")
            return 0
        if args.cmd == "release":
            note = load_note(args.number)
            if args.update_notes:
                release.update_notes(note)
                return 0
            if not args.dry_run and not show(run_checks([note.number], online=True, rebuild=True)):
                raise PipelineError("checks failed; not releasing")
            release.create(note, dry_run=args.dry_run)
            return 0
        if args.cmd == "zenodo":
            note = load_note(args.number)
            return zenodo.run(note, env="sandbox" if args.sandbox else "production", publish=args.publish,
                              confirm_doi=args.confirm_doi, dry_run=args.dry_run)
    except PipelineError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
