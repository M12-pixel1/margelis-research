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
        metadata = build_metadata(note, info["pages"], tmp_pdf)
        tmp_meta = Path(tmp) / "metadata.json"
        write_json(tmp_meta, metadata)
        sums = {note.md_path.name: sha256_file(note.md_path),
                note.pdf_path.name: sha256_file(tmp_pdf),
                note.metadata_path.name: sha256_file(tmp_meta)}
        sums_text = "".join(f"{d}  {n}\n" for n, d in sums.items())
        prior = released_sums(note)
        if prior is not None and prior.strip() != sums_text.strip():
            raise PipelineError(
                f"{note.tag} is already released and this build would change its artifacts. "
                "Published versions are never overwritten: add a new version (e.g. 1.1) to note.yaml.")
        shutil.copyfile(tmp_pdf, note.pdf_path)
        shutil.copyfile(tmp_meta, note.metadata_path)
    write_text(note.sums_path, sums_text)

    vdir = note.site_version_dir
    vdir.mkdir(parents=True, exist_ok=True)
    for f in (note.md_path, note.pdf_path, note.metadata_path, note.sums_path):
        shutil.copyfile(f, vdir / f.name)
    site.render_og_image(note, note.site_dir / note.og_image_name)
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
    written.append(ROOT / "CITATION.cff")
    return written
