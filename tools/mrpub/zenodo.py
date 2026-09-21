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
        + " ".join((note.meta["zenodo"].get("description_addendum_html") or "").split())
        + f"<p>{e(note.series_name)} Note {e(note.number)}, version {e(note.version)}, published by "
        f"{e(note.publisher)}. Canonical page: <a href=\"{e(note.canonical_url)}\">{e(note.canonical_url)}</a>. "
        f"Source and release: <a href=\"{e(note.release_url)}\">{e(note.release_url)}</a>.</p>"
        f"<p>The SHA-256 digests of the files in this record are listed in SHA256SUMS; the same bytes are "
        f"attached to the GitHub release.</p>"
        + version_changes_html(note)
    )


def version_changes_html(note: Note) -> str:
    """For versions after the first: what changed and which DOI this version supersedes."""
    e = lambda s: html.escape(str(s), quote=False)  # noqa: E731
    current = next(h for h in note.meta["version_history"] if str(h["version"]) == note.version)
    previous = note.previous_versions()
    if not previous:
        return ""
    prev = previous[-1]
    prev_doi = note.version_doi(prev)
    changes = current.get("changes") or [current["summary"]]
    items = "".join(f"<li>{e(c)}</li>" for c in changes)
    supersedes = f" (DOI {e(prev_doi)})" if prev_doi else ""
    return (f"<p><strong>Changes in version {e(note.version)}</strong> (supersedes version {e(prev)}{supersedes}; "
            f"earlier versions remain available unchanged):</p><ul>{items}</ul>")


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

    def newversion(self, dep_id: int) -> dict:
        """Returns the ORIGINAL deposition; the new draft is at links.latest_draft."""
        return self._check(self.s.post(f"{self.base}/deposit/depositions/{dep_id}/actions/newversion",
                                       timeout=120), 201)

    def get_url(self, url: str) -> dict:
        if not url.startswith(self.base + "/"):
            raise PipelineError(f"refusing to follow a URL outside {self.base}: {url}")
        return self._check(self.s.get(url, timeout=60), 200)

    def delete_file(self, dep_id: int, file_id: str) -> None:
        self._check(self.s.delete(f"{self.base}/deposit/depositions/{dep_id}/files/{file_id}", timeout=60), 204)

    def list_depositions(self) -> list[dict]:
        out, page = [], 1
        while True:
            r = self.s.get(f"{self.base}/deposit/depositions",
                           params={"page": page, "size": 100, "all_versions": "true"}, timeout=60)
            batch = self._check(r, 200)
            out += batch
            if len(batch) < 100:
                return out
            page += 1


PIPELINE_OWNED = ("upload_type", "publication_type", "title", "creators", "description", "publication_date",
                  "version", "language", "keywords", "notes", "related_identifiers", "references",
                  "access_right", "license")


def description_text(html_text: str) -> str:
    """Tag-stripped, whitespace-normalised text, which is what Zenodo preserves."""
    import re
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", html_text or "")).split())


def metadata_diff(note: Note, live: dict) -> dict[str, tuple]:
    """Pipeline-owned fields whose live value differs from what the pipeline generates."""
    expected = build_metadata(note)
    diffs = {}
    live = dict(live)
    if "resource_type" in live and "upload_type" not in live:
        # the public records API nests the type; the deposit API uses upload_type/publication_type
        rt = live.get("resource_type") or {}
        live["upload_type"], live["publication_type"] = rt.get("type"), rt.get("subtype")
    for key in PIPELINE_OWNED:
        want = expected.get(key)
        have = live.get(key)
        if key == "description":
            if description_text(str(have or "")) != description_text(str(want or "")):
                diffs[key] = (description_text(str(have or ""))[:200], description_text(str(want or ""))[:200])
        elif key == "license":
            have_id = have.get("id") if isinstance(have, dict) else have
            if str(have_id or "").lower() != str(want or "").lower():
                diffs[key] = (have, want)
        elif key in ("creators", "related_identifiers"):
            norm = lambda v: [{k: x[k] for k in sorted(x) if k in ("name", "affiliation", "orcid", "identifier", "relation")}  # noqa: E731
                              for x in (v or [])]
            if norm(have) != norm(want):
                diffs[key] = (have, want)
        elif have != want:
            diffs[key] = (have, want)
    return diffs


def edit_metadata(note: Note, env: str = "production", apply: bool = False, confirm_doi: str | None = None) -> int:
    """Bring the PUBLISHED record's metadata in line with the pipeline (no new version, DOI unchanged).

    Dry run by default: prints the differences. --apply --confirm-doi <DOI of the record> performs
    actions/edit -> PUT metadata -> actions/publish and verifies the result.
    """
    rec = note.zenodo_record()
    if not rec or rec.get("state") != "published":
        raise PipelineError(f"note {note.number} v{note.version} has no published Zenodo record to edit")
    try:
        client = Client(env)
    except LookupError:
        print(token_instructions(note, env))
        return EXIT_BLOCKED
    dep = client.get(rec["deposition_id"])
    live = dep["metadata"]
    diffs = metadata_diff(note, live)
    if not diffs:
        print(f"Zenodo record {rec['deposition_id']} ({rec.get('doi')}) already matches the pipeline metadata.")
        return 0
    print(f"Record {rec['deposition_id']} ({rec.get('doi')}) differs from the pipeline in: {sorted(diffs)}")
    for key, (have, want) in diffs.items():
        print(f"  {key}:\n    live:     {str(have)[:300]}\n    pipeline: {str(want)[:300]}")
    if not apply:
        print("Dry run. To apply (metadata only, DOI unchanged):\n"
              f"  python tools/publish.py zenodo-edit-metadata {note.number} --apply --confirm-doi {rec.get('doi')}")
        return 0
    if confirm_doi != rec.get("doi"):
        raise PipelineError(f"--confirm-doi {confirm_doi!r} does not match the record DOI {rec.get('doi')!r}; not editing")
    new_meta = {k: v for k, v in live.items() if k != "prereserve_doi"}
    new_meta.update({k: v for k, v in build_metadata(note).items() if k in PIPELINE_OWNED})
    client._check(client.s.post(f"{client.base}/deposit/depositions/{dep['id']}/actions/edit", timeout=60), 200, 201)
    client.update(dep["id"], new_meta)
    client.publish(dep["id"])
    after = client.get(dep["id"])["metadata"]
    remaining = metadata_diff(note, after)
    if remaining:
        raise PipelineError(f"after publishing, these fields still differ: {sorted(remaining)}")
    print(f"Record {rec['deposition_id']} metadata updated and republished; DOI {rec.get('doi')} unchanged.")
    return 0


def sync_from_workflow(note: Note) -> str:
    """Copy research/<NNN>/zenodo.json from the newest publish-note run that uploaded it (workflow runs
    cannot push to the protected main branch, so the record is committed through a pull request)."""
    import subprocess
    import tempfile
    import shutil
    from pathlib import Path
    runs = subprocess.run(["gh", "run", "list", "-R", note.repo_slug, "--workflow", "publish-note.yml",
                           "--limit", "20", "--json", "databaseId,conclusion,createdAt"],
                          capture_output=True, text=True, encoding="utf-8")
    if runs.returncode != 0:
        raise PipelineError(f"gh run list failed: {runs.stderr.strip()}")
    for run in json.loads(runs.stdout or "[]"):
        with tempfile.TemporaryDirectory() as tmp:
            dl = subprocess.run(["gh", "run", "download", str(run["databaseId"]), "-R", note.repo_slug,
                                 "-n", f"zenodo-{note.number}", "-D", tmp], capture_output=True, text=True)
            if dl.returncode != 0:
                continue  # this run did not upload the artifact
            src = Path(tmp) / note.number / "zenodo.json"
            if not src.exists():
                continue
            shutil.copyfile(src, note.zenodo_path)
            records = note.zenodo_records()
            return (f"research/{note.number}/zenodo.json updated from run {run['databaseId']} ({run['createdAt']}): "
                    + ", ".join(f"v{v} {r.get('state')} {r.get('doi') or r.get('reserved_doi') or ''}".strip()
                                for v, r in records.items()))
    raise PipelineError(f"no publish-note run with a zenodo-{note.number} artifact found")


def account_status(note: Note, env: str = "production") -> int:
    """Read-only. Workflow logs of a public repository are public, so only depositions that belong
    to this note are described; any other deposition (e.g. unrelated private drafts) is only counted."""
    try:
        client = Client(env)
    except LookupError:
        print(token_instructions(note, env))
        return EXIT_BLOCKED
    known = {r.get("deposition_id") for r in note.zenodo_records().values()}
    mine, others = [], 0
    for d in client.list_depositions():
        md = d.get("metadata", {})
        if d.get("id") in known or d.get("title") == note.full_title or md.get("title") == note.full_title:
            mine.append({"deposition_id": d.get("id"), "state": d.get("state"), "submitted": d.get("submitted"),
                         "version": md.get("version"), "publication_date": md.get("publication_date"),
                         "doi": d.get("doi") or None,
                         "reserved_doi": (md.get("prereserve_doi") or {}).get("doi"),
                         "tracked_in_zenodo_json": d.get("id") in known})
        else:
            others += 1
    unpublished = [m for m in mine if not m["submitted"]]
    print(json.dumps({"environment": env, "account_access": "PASS", "note_depositions": mine,
                      "unpublished_note_drafts": len(unpublished),
                      "untracked_note_depositions": sum(1 for m in mine if not m["tracked_in_zenodo_json"]),
                      "other_depositions_not_inspected": others}, indent=2))
    return 0


def save_record(note: Note, state: dict) -> None:
    """zenodo.json keeps one record per version: {"records": {"1.0": {...}, "1.1": {...}}}."""
    records = dict(note.zenodo_records())
    records[note.version] = state
    write_json(note.zenodo_path, {"records": dict(sorted(records.items(), key=lambda kv: [int(x) for x in kv[0].split(".")]))})


def compare(expected: dict, remote: dict) -> list[str]:
    diffs = []
    for key in ("upload_type", "publication_type", "title", "publication_date", "version", "access_right",
                "language", "keywords"):
        if key in expected and remote.get(key) != expected[key]:
            diffs.append(f"{key}: expected {expected[key]!r}, Zenodo has {remote.get(key)!r}")
    remote_license = remote.get("license")
    if isinstance(remote_license, dict):  # the API may return {"id": "cc-by-4.0", ...}
        remote_license = remote_license.get("id")
    if expected.get("license") and str(remote_license or "").lower() != expected["license"]:
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
    previous = None
    if dep is None:
        published = [(v, r) for v, r in note.zenodo_records().items()
                     if v != note.version and r.get("environment") == env and r.get("state") == "published"]
        if published:
            # a later version of an archived note: new version of the same Zenodo concept
            previous, prev_rec = max(published, key=lambda vr: [int(x) for x in vr[0].split(".")])
            original = client.newversion(prev_rec["deposition_id"])
            dep = client.get_url(original["links"]["latest_draft"])
        else:
            dep = client.create()
        # record the draft at once so that a later failure never leaves an untracked deposition
        save_record(note, {"environment": env, "version": note.version, "deposition_id": dep["id"],
                           "previous_version": previous, "state": "draft-created", "checked_at": utc_now()})
        print(f"Created draft deposition {dep['id']}"
              + (f" as a new version of v{previous} (deposition {prev_rec['deposition_id']})" if previous else ""))
        if previous:
            # the new-version draft starts with a snapshot of the previous files
            for f in dep.get("files", []):
                client.delete_file(dep["id"], f["id"])
                print(f"Removed inherited file {f['filename']}")
            dep = client.get(dep["id"])
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
    extra = sorted(set(remote_files) - {f.name for f in files})
    if extra:
        diffs.append(f"unexpected files on Zenodo: {extra}")
    state = {
        "environment": env,
        "version": note.version,
        "previous_version": (record or {}).get("previous_version", previous),
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
    save_record(note, state)
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
    save_record(note, state)
    print(f"Published: {state['doi_url']}  state={state['state']}")
    print(f"Next: python tools/publish.py build {note.number} && python tools/publish.py receipt {note.number}")
    return 0 if state["state"] == "published" else 1
