"""Build step: PDF -> metadata.json -> SHA256SUMS -> web pages -> CITATION.cff."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from . import citation, site
from .common import (ROOT, SITE, Note, PipelineError, epoch_of, git, load_json, load_note, parse_sums,
                     sha256_file, write_json, write_text)
from .pdf import render_pdf

MEDIA = {".md": "text/markdown; charset=utf-8", ".pdf": "application/pdf"}


def _file_entry(path: Path, role: str, pages: int | None = None) -> dict:
    entry = {"path": path.name, "role": role, "media_type": MEDIA[path.suffix],
             "bytes": path.stat().st_size, "sha256": sha256_file(path)}
    if pages:
        entry["pages"] = pages
    return entry


def build_metadata(note: Note, pdf_pages: int | None, pdf_path: Path | None = None) -> dict:
    pdf_path = pdf_path or note.pdf_path
    lic = note.license
    pdf_entry = _file_entry(pdf_path, "rendition", pdf_pages)
    pdf_entry["path"] = note.pdf_path.name
    return {
        "schema": "margelis-research/note-metadata/1",
        "id": f"margelis-research-note-{note.number}",
        "series": note.series_name,
        "number": note.number,
        "version": note.version,
        "release_tag": note.tag,
        "title": note.full_title,
        "short_title": note.title,
        "subtitle": note.subtitle,
        "authors": [{"name": f"{a['given_name']} {a['family_name']}", "given_name": a["given_name"],
                     "family_name": a["family_name"], "affiliation": a["affiliation"], "orcid": a.get("orcid")}
                    for a in note.authors],
        "publisher": note.publisher,
        "publication_date": note.date,
        "language": note.meta.get("language", "en"),
        "publication_type": note.meta["publication_type"],
        "archive_resource_type": {"zenodo_upload_type": note.meta["zenodo"]["upload_type"],
                                  "zenodo_publication_type": note.meta["zenodo"]["publication_type"]},
        "status": note.meta["status"],
        "abstract": " ".join(note.meta["abstract"].split()),
        "keywords": list(note.meta["keywords"]),
        "license": {"status": lic["status"], "spdx": lic.get("spdx"), "proposed": lic.get("proposed"),
                    "scope": " ".join(lic["scope"].split())},
        "canonical_url": note.canonical_url,
        "repository_url": note.repo_url,
        "release_url": note.release_url,
        "persistent_identifiers": ("Identifiers assigned after release (such as a DOI) are recorded in "
                                   "publication-receipt.json and CITATION.cff. This manifest is immutable per version."),
        "files": [_file_entry(note.md_path, "source"), pdf_entry],
        "build": {
            "command": f"python tools/publish.py build {note.number}",
            "renderer": "ReportLab 4.5.0 (invariant mode, uncompressed streams), markdown-it-py 4.0.0",
            "fonts": "DejaVu 2.35 (tools/fonts), embedded subsets",
            "source_date_epoch": epoch_of(note.date),
            "rebuild_check": f"python tools/publish.py verify {note.number} --rebuild",
        },
        "references": load_json(note.references_path)["references"],
        "version_history": [{"version": str(h["version"]), "date": str(h["date"]), "summary": h["summary"],
                             "release_tag": f"research-note-{note.number}-v{h['version']}"}
                            for h in note.meta["version_history"]],
    }


def released_sums(note: Note) -> str | None:
    if not git("tag", "-l", note.tag, check=False):
        return None
    return git("show", f"{note.tag}:research/{note.number}/SHA256SUMS", check=False) or None


def build_note(note: Note) -> dict:
    if str(note.meta["version_history"][-1]["version"]) != note.version:
        raise PipelineError("the last version_history entry must describe the current version")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_pdf = Path(tmp) / note.pdf_path.name
        info = render_pdf(note, tmp_pdf)
        prior = released_sums(note)
        if prior is not None:
            # Released: the manifest records the state at release time (DOI and license
            # decisions made later live in the receipt, CITATION.cff, LICENSE and the web page).
            # Rebuild only to prove that nothing changed.
            sums = {line.split(maxsplit=1)[1].strip(): line.split()[0] for line in prior.splitlines() if line.strip()}
            now = {note.md_path.name: sha256_file(note.md_path), note.pdf_path.name: sha256_file(tmp_pdf),
                   note.metadata_path.name: sha256_file(note.metadata_path) if note.metadata_path.exists() else None}
            changed = sorted(name for name, digest in sums.items() if now.get(name) != digest)
            if changed:
                raise PipelineError(
                    f"{note.tag} is already released and this build would change {changed}. "
                    "Published versions are never overwritten: add a new version (e.g. 1.1) to note.yaml.")
            sums_text = prior.strip() + "\n"
        else:
            metadata = build_metadata(note, info["pages"], tmp_pdf)
            tmp_meta = Path(tmp) / "metadata.json"
            write_json(tmp_meta, metadata)
            sums = {note.md_path.name: sha256_file(note.md_path),
                    note.pdf_path.name: sha256_file(tmp_pdf),
                    note.metadata_path.name: sha256_file(tmp_meta)}
            sums_text = "".join(f"{d}  {n}\n" for n, d in sums.items())
            shutil.copyfile(tmp_meta, note.metadata_path)
        shutil.copyfile(tmp_pdf, note.pdf_path)
    write_text(note.sums_path, sums_text)

    vdir = note.site_version_dir
    vdir.mkdir(parents=True, exist_ok=True)
    for f in (note.md_path, note.pdf_path, note.metadata_path, note.sums_path):
        shutil.copyfile(f, vdir / f.name)
    og = note.site_dir / note.og_image_name
    if not og.exists():  # per-version card; re-rendering elsewhere only changes anti-aliasing bytes
        site.render_og_image(note, og)
    return {"note": note.number, "version": note.version, "pages": info["pages"], "sha256": sums}


def build_site_and_citation() -> list[Path]:
    from .common import all_notes
    notes = [load_note(n) for n in all_notes()]
    per_note = {}
    for n in notes:
        if not n.metadata_path.exists():
            raise PipelineError(f"note {n.number} has not been built")
        per_note[n.number] = (load_json(n.metadata_path), parse_sums(n.sums_path))
    written = site.write_site(notes, notes[0].series, per_note, SITE)
    citation.write(notes)
    write_text(ROOT / "LICENSE", license_text(notes))
    written += [ROOT / "CITATION.cff", ROOT / "LICENSE"]
    return written


LICENSE_NAMES = {
    "CC-BY-4.0": ("Creative Commons Attribution 4.0 International",
                  "https://creativecommons.org/licenses/by/4.0/legalcode"),
}
FONTS_NOTICE = """Third-party material with its own license:

  tools/fonts/*.ttf   DejaVu fonts 2.35, see tools/fonts/LICENSE-DejaVu.txt
"""


def license_text(notes: list[Note]) -> str:
    """LICENSE is generated: nothing is licensed until note.yaml records an explicit grant."""
    granted = [n for n in notes if n.license_granted]
    if not granted:
        scope = " ".join(notes[-1].license["scope"].split())
        proposed = notes[-1].license.get("proposed") or "none"
        return f"""LICENSE STATUS: PENDING

No license has been granted yet for the contents of this repository.

A license decision is pending. Until a license is published in this file, the
contents are made available for reading only, and all other rights are reserved
by the rights holder(s).

Proposed, not granted: {proposed}.
Scope of the proposal: {scope}

{FONTS_NOTICE}"""
    parts = ["LICENSE\n", "1. Margelis Research Note text\n"]
    for n in granted:
        spdx = n.license["spdx"]
        name, url = LICENSE_NAMES.get(spdx, (spdx, f"https://spdx.org/licenses/{spdx}.html"))
        a = n.authors[0]
        parts.append(
            f"The files\n\n  research/{n.number}/{n.md_path.name}\n  research/{n.number}/{n.pdf_path.name}\n\n"
            f"are licensed under the {name} license ({spdx}):\n{url}\n\n"
            f"Granted by {n.license['authorized_by']} on {n.license['authorized_on']}.\n"
            f"Attribution: {a['family_name']}, {a['given_name'][0]}. ({n.date[:4]}). {n.full_title} "
            f"({n.series_name} Note {n.number}). {n.publisher}.\n"
            f"Scope: {' '.join(n.license['scope'].split())}\n")
    pending = [n for n in notes if not n.license_granted]
    parts.append("2. Everything else\n")
    parts.append("No license has been granted for any other content of this repository (pipeline code, "
                 "schemas, benchmark specifications, generated web pages"
                 + (", and the notes " + ", ".join(n.number for n in pending) if pending else "")
                 + "). All rights in that content are reserved by the rights holder(s).\n")
    parts.append("3. " + FONTS_NOTICE)
    return "\n".join(parts)
