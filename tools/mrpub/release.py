"""GitHub release for a note version: draft -> attach assets -> publish -> verify downloads.

Never overwrites: refuses when the tag already exists. With immutable releases enabled on the
repository, the published tag and assets are locked by GitHub; only the notes can be edited.
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from . import receipt
from .common import Note, PipelineError, git, human_date, parse_sums, sha256_file, write_text


def _gh(*args: str) -> str:
    r = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise PipelineError(f"gh {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout.strip()


def notes_markdown(note: Note) -> str:
    sums = parse_sums(note.sums_path)
    pdf_sha = sums[note.pdf_path.name]
    canonical = receipt.probe_canonical(note, pdf_sha)
    rec = receipt.probe_zenodo(note)
    immutable, _ = receipt.gh_api(f"repos/{note.repo_slug}/immutable-releases")
    a = note.authors[0]
    page = note.canonical_url if canonical["status"] == "LIVE" else \
        f"{note.canonical_url} (deployment pending; mirror: {note.preview_url})"
    doi = f"https://doi.org/{rec['doi']}" if rec.get("doi") else "Pending (the Zenodo record has not been published yet)"
    lic = f"{note.license['spdx']} (note text only)" if note.license_granted else \
        "Not yet granted (license decision pending)"
    unproven = note.meta.get("locked_statements", {}).get("What remains unproven", [])
    rows = "\n".join(f"| `{name}` | `{digest}` |" for name, digest in sums.items())
    lines = [
        f"**{note.series_name} Note {note.number}: {note.full_title}**",
        "",
        "| | |",
        "| --- | --- |",
        f"| Publication type | Research note ({note.series_name}) |",
        f"| Version | {note.version} |",
        f"| Date | {human_date(note.date)} |",
        f"| Author | {a['given_name']} {a['family_name']}, {a['affiliation']} |",
        f"| Status | {note.meta['status']} |",
        f"| DOI | {doi} |",
        f"| Canonical web page | {page} |",
        f"| License | {lic} |",
        "",
        " ".join(note.meta["abstract"].split()),
        "",
        "### Limitations (What remains unproven)",
        "",
        *[f"- {s}" for s in unproven],
        "",
        "This note defines an evaluation framework and reports no benchmark results.",
        "",
        "### Files",
        "",
        "| File | SHA-256 |",
        "| --- | --- |",
        rows,
        "",
        "Verify after download:",
        "",
        "```bash",
        "sha256sum -c SHA256SUMS",
        f"gh release verify {note.tag} -R {note.repo_slug}",
        "```",
    ]
    if (immutable or {}).get("enabled"):
        lines += ["", "This is an immutable release: its tag and files cannot be changed. "
                      "Corrections are published as a new version."]
    return "\n".join(lines) + "\n"


def create(note: Note, dry_run: bool = False) -> dict:
    tag = note.tag
    if git("status", "--porcelain", check=False):
        raise PipelineError("working tree is not clean; commit the built artifacts first")
    head = git("rev-parse", "HEAD")
    git("fetch", "origin", "--tags", "--quiet", check=False)
    if not git("branch", "-r", "--contains", head, check=False):
        raise PipelineError(f"HEAD {head[:12]} is not on origin; push first")
    if git("tag", "-l", tag, check=False) or git("ls-remote", "--tags", "origin", f"refs/tags/{tag}", check=False):
        raise PipelineError(f"{tag} already exists; published versions are never overwritten")
    files = [note.pdf_path, note.md_path, note.metadata_path, note.sums_path]
    body = notes_markdown(note)
    title = f"{note.series_name} Note {note.number}: {note.title}"
    if dry_run:
        print(f"[dry-run] would create {tag} at {head} titled {title!r} with {[f.name for f in files]}\n")
        print(body)
        return {"dry_run": True}
    with tempfile.TemporaryDirectory() as tmp:
        notes_file = Path(tmp) / "notes.md"
        write_text(notes_file, body)
        _gh("release", "create", tag, "--repo", note.repo_slug, "--target", head, "--title", title,
            "--notes-file", str(notes_file), "--draft", *[str(f) for f in files])
    _gh("release", "edit", tag, "--repo", note.repo_slug, "--draft=false")
    git("fetch", "origin", "--tags", "--quiet", check=False)
    result = receipt.probe_release(note)
    if not result.get("all_assets_present_and_matching") or result.get("draft"):
        raise PipelineError(f"release verification failed: {result}")
    print(f"Released {tag}: {result['url']} (immutable={result.get('immutable')}); all assets match SHA256SUMS")
    return result


def update_notes(note: Note) -> None:
    """Refresh release notes (e.g. after DOI assignment). Assets and tag are untouched."""
    with tempfile.TemporaryDirectory() as tmp:
        notes_file = Path(tmp) / "notes.md"
        write_text(notes_file, notes_markdown(note))
        _gh("release", "edit", note.tag, "--repo", note.repo_slug, "--notes-file", str(notes_file))
    print(f"Updated notes of {note.tag}")


def local_asset_digests(note: Note) -> dict[str, str]:
    return {f.name: sha256_file(f) for f in (note.pdf_path, note.md_path, note.metadata_path, note.sums_path)}
