"""Zenodo deposition via the official REST API (https://developers.zenodo.org/).

Safety properties
  * The token is read from the environment only and never printed.
  * Without a granted license the draft is created with access_right=closed
    (Zenodo would otherwise default publications to CC-BY) and publishing is refused.
  * Publishing requires --publish AND --confirm-doi equal to the DOI reserved
    for the draft, i.e. a human who has looked at the draft.
  * Uploaded files are verified by MD5 against the local files, and the local
    files are verified against SHA256SUMS before anything is sent.
"""
from __future__ import annotations

import html
import json
import os

import requests

from .common import Note, PipelineError, load_json, md5_file, parse_sums, sha256_file, utc_now, write_json

API = {"production": "https://zenodo.org/api", "sandbox": "https://sandbox.zenodo.org/api"}
WEB = {"production": "https://zenodo.org", "sandbox": "https://sandbox.zenodo.org"}
TOKEN_ENV = {"production": "ZENODO_ACCESS_TOKEN", "sandbox": "ZENODO_SANDBOX_TOKEN"}
LANG3 = {"en": "eng", "lt": "lit"}

EXIT_BLOCKED = 3


def token_instructions(note: Note, env: str) -> str:
    web = WEB[env]
    var = TOKEN_ENV[env]
    return f"""BLOCKED: {var} is not set.

One manual step (Tomas):
  1. Sign in at {web}/ (a GitHub or ORCID login works).
  2. Open {web}/account/settings/applications/tokens/new/
     Name: margelis-research-publisher
     Scopes: deposit:write and deposit:actions (nothing else).
  3. Store the token without printing it:
       gh secret set {var} -R {note.repo_slug}     (paste when prompted)
     and, for a local run, in the current PowerShell session only:
       $env:{var} = Read-Host -AsSecureString | ConvertFrom-SecureString -AsPlainText
  4. Rerun:
       python tools/publish.py zenodo {note.number}{' --sandbox' if env == 'sandbox' else ''}
     This creates a private draft, reserves the DOI and uploads the files. Nothing is published.
  5. After reviewing the draft and granting the license in research/{note.number}/note.yaml:
       python tools/publish.py zenodo {note.number} --publish --confirm-doi <reserved DOI>
"""


def description_html(note: Note) -> str:
    e = lambda s: html.escape(str(s), quote=False)  # noqa: E731
    unproven = note.meta.get("locked_statements", {}).get("What remains unproven", [])
    items = "".join(f"<li>{e(s)}</li>" for s in unproven)
    return (
        f"<p>{e(' '.join(note.meta['abstract'].split()))}</p>"
        f"<p><strong>Status:</strong> {e(note.meta['status'])}. This note defines an evaluation framework and "
        f"reports no benchmark results.</p>"
        f"<p><strong>What remains unproven:</strong></p><ul>{items}</ul>"
        f"<p>{e(note.series_name)} Note {e(note.number)}, version {e(note.version)}, published by "
        f"{e(note.publisher)}. Canonical page: <a href=\"{e(note.canonical_url)}\">{e(note.canonical_url)}</a>. "
        f"Source and release: <a href=\"{e(note.release_url)}\">{e(note.release_url)}</a>.</p>"
        f"<p>The SHA-256 digests of the files in this record are listed in SHA256SUMS; the same bytes are "
        f"attached to the GitHub release.</p>"
    )


def build_metadata(note: Note) -> dict:
    refs = load_json(note.references_path)["references"] if note.references_path.exists() else []
    related = [
        {"identifier": note.canonical_url, "relation": "isVariantFormOf"},
        {"identifier": note.release_url, "relation": "isIdenticalTo"},
        {"identifier": note.repo_url, "relation": "isSupplementedBy"},
    ]
    references = []
    for r in refs:
        ident = r.get("identifier", "")
        related.append({"identifier": ident if ident.startswith("arXiv:") else r["url"], "relation": "cites"})
        who = "; ".join(r.get("authors", [])) or r.get("publisher", "")
        when = r.get("date", "")
        references.append(" ".join(x for x in [
            f"{who}." if who else "", f"({when[:4]})." if when else "", f"{r['title']}.",
            f"{ident}." if ident else "", r.get("status", "") + ("." if r.get("status") else ""), r["url"],
        ] if x).strip())
    meta = {
        "upload_type": note.meta["zenodo"]["upload_type"],
        "publication_type": note.meta["zenodo"]["publication_type"],
        "title": note.full_title,
        "creators": [
            {"name": f"{a['family_name']}, {a['given_name']}", "affiliation": a["affiliation"],
             **({"orcid": a["orcid"]} if a.get("orcid") else {})}
            for a in note.authors
        ],
        "description": description_html(note),
        "publication_date": note.date,
        "version": note.version,
        "language": LANG3.get(note.meta.get("language", "en"), "eng"),
        "keywords": list(note.meta["keywords"]),
        "notes": f"Status: {note.meta['status']}. No benchmark results are reported. "
                 f"See the section 'What remains unproven'.",
        "related_identifiers": related,
        "references": references,
        "prereserve_doi": True,
    }
    if note.license_granted:
        meta["access_right"] = "open"
        meta["license"] = note.license["spdx"].lower()
    else:
        meta["access_right"] = "closed"
    return meta


def upload_files(note: Note) -> list:
    sums = parse_sums(note.sums_path)
    files = [note.md_path, note.pdf_path, note.metadata_path, note.sums_path]
    for f in files[:-1]:
        if sums.get(f.name) != sha256_file(f):
            raise PipelineError(f"{f.name} does not match SHA256SUMS; run `publish.py build {note.number}` first")
    return files


class Client:
    def __init__(self, env: str):
        token = os.environ.get(TOKEN_ENV[env], "").strip()
        if not token:
            raise LookupError(TOKEN_ENV[env])
        self.base = API[env]
        self.s = requests.Session()
        self.s.headers["Authorization"] = f"Bearer {token}"

    def _check(self, r: requests.Response, *ok: int) -> dict:
        if r.status_code not in ok:
            body = r.text[:800]
            raise PipelineError(f"Zenodo {r.request.method} {r.url} -> HTTP {r.status_code}: {body}")
        return r.json() if r.content else {}

    def create(self) -> dict:
        return self._check(self.s.post(f"{self.base}/deposit/depositions", json={}, timeout=60), 201)

    def get(self, dep_id: int) -> dict:
        return self._check(self.s.get(f"{self.base}/deposit/depositions/{dep_id}", timeout=60), 200)

    def update(self, dep_id: int, metadata: dict) -> dict:
        return self._check(self.s.put(f"{self.base}/deposit/depositions/{dep_id}",
                                      json={"metadata": metadata}, timeout=60), 200)

    def upload(self, bucket: str, path) -> dict:
        with open(path, "rb") as fh:
            return self._check(self.s.put(f"{bucket}/{path.name}", data=fh, timeout=300), 200, 201)

    def publish(self, dep_id: int) -> dict:
        return self._check(self.s.post(f"{self.base}/deposit/depositions/{dep_id}/actions/publish", timeout=120), 202)


def compare(expected: dict, remote: dict) -> list[str]:
    diffs = []
    for key in ("upload_type", "publication_type", "title", "publication_date", "version", "access_right",
                "language", "keywords"):
        if key in expected and remote.get(key) != expected[key]:
            diffs.append(f"{key}: expected {expected[key]!r}, Zenodo has {remote.get(key)!r}")
    if expected.get("license") and (remote.get("license") or {}) != expected["license"] \
            and str(remote.get("license", "")).lower() != expected["license"]:
        diffs.append(f"license: expected {expected['license']!r}, Zenodo has {remote.get('license')!r}")
    exp_creators = [(c["name"], c.get("affiliation")) for c in expected["creators"]]
    rem_creators = [(c.get("name"), c.get("affiliation")) for c in remote.get("creators", [])]
    if exp_creators != rem_creators:
        diffs.append(f"creators: expected {exp_creators}, Zenodo has {rem_creators}")
    return diffs


def run(note: Note, env: str = "production", publish: bool = False, confirm_doi: str | None = None,
        dry_run: bool = False) -> int:
    metadata = build_metadata(note)
    files = upload_files(note)
    if dry_run:
        print(json.dumps({"environment": env, "metadata": metadata, "files": [f.name for f in files]},
                         ensure_ascii=False, indent=2))
        return 0
    if publish and not note.license_granted:
        raise PipelineError("refusing to publish: license status is not 'granted' in note.yaml "
                            "(Zenodo would otherwise apply its default license)")
    try:
        client = Client(env)
    except LookupError:
        print(token_instructions(note, env))
        return EXIT_BLOCKED

    record = note.zenodo_record()
    dep = None
    if record and record.get("environment") == env and record.get("version") == note.version:
        dep = client.get(record["deposition_id"])
        if dep.get("submitted"):
            print(f"Already published: {dep.get('doi')} ({dep['links'].get('html')}). Nothing to do.")
            return 0
    if dep is None:
        dep = client.create()
        print(f"Created draft deposition {dep['id']}")
    dep = client.update(dep["id"], metadata)
    reserved = dep["metadata"].get("prereserve_doi", {}).get("doi")

    present = {f["filename"]: f["checksum"] for f in dep.get("files", [])}
    for f in files:
        md5 = md5_file(f)
        if present.get(f.name, "").removeprefix("md5:") == md5:
            continue
        up = client.upload(dep["links"]["bucket"], f)
        got = str(up.get("checksum", "")).removeprefix("md5:")
        if got != md5:
            raise PipelineError(f"upload checksum mismatch for {f.name}: local {md5}, Zenodo {got}")
        print(f"Uploaded {f.name} (md5 {md5})")

    dep = client.get(dep["id"])
    diffs = compare(metadata, dep["metadata"])
    remote_files = {f["filename"]: f["checksum"].removeprefix("md5:") for f in dep.get("files", [])}
    for f in files:
        if remote_files.get(f.name) != md5_file(f):
            diffs.append(f"file {f.name}: missing or checksum differs on Zenodo")
    state = {
        "environment": env,
        "version": note.version,
        "deposition_id": dep["id"],
        "record_id": dep.get("record_id"),
        "concept_record_id": dep.get("conceptrecid"),
        "reserved_doi": reserved,
        "state": "draft",
        "draft_url": dep["links"].get("html"),
        "access_right": metadata["access_right"],
        "license": metadata.get("license"),
        "files": [{"filename": f.name, "md5": md5_file(f), "sha256": sha256_file(f)} for f in files],
        "metadata_matches": not diffs,
        "checked_at": utc_now(),
    }
    write_json(note.zenodo_path, state)
    if diffs:
        raise PipelineError("Zenodo draft does not match local metadata:\n  " + "\n  ".join(diffs))
    print(f"Draft verified. Reserved DOI: {reserved} (not registered until published). Review: {state['draft_url']}")

    if not publish:
        print("Stopped before publication (irreversible). To publish after review:\n"
              f"  python tools/publish.py zenodo {note.number}"
              f"{' --sandbox' if env == 'sandbox' else ''} --publish --confirm-doi {reserved}")
        return 0
    if confirm_doi != reserved:
        raise PipelineError(f"--confirm-doi {confirm_doi!r} does not match the reserved DOI {reserved!r}; not publishing")
    client.publish(dep["id"])
    dep = client.get(dep["id"])
    state.update({
        "state": "published" if dep.get("submitted") else "unknown",
        "doi": dep.get("doi") or reserved,
        "doi_url": dep.get("doi_url") or f"https://doi.org/{reserved}",
        "record_url": dep["links"].get("record_html") or dep["links"].get("html"),
        "concept_doi": dep.get("conceptdoi"),
        "published_at": utc_now(),
    })
    write_json(note.zenodo_path, state)
    print(f"Published: {state['doi_url']}  state={state['state']}")
    print(f"Next: python tools/publish.py build {note.number} && python tools/publish.py receipt {note.number}")
    return 0 if state["state"] == "published" else 1
