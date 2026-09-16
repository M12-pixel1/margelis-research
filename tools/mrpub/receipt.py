"""publication-receipt.json: where a note version is published, with every fact probed at generation time.

Nothing is copied from local state files without re-checking it against the external system.
"""
from __future__ import annotations

import json
import subprocess

import requests

from .checks import UA, Result
from .common import Note, parse_sums, sha256_bytes, sha256_file, utc_now, write_json

ZENODO_PUBLIC = {"production": "https://zenodo.org/api/records/", "sandbox": "https://sandbox.zenodo.org/api/records/"}


def gh_api(path: str):
    r = subprocess.run(["gh", "api", path], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        return None, (r.stderr or r.stdout).strip().splitlines()[-1][:200] if (r.stderr or r.stdout) else "error"
    return json.loads(r.stdout or "null"), None


def http_probe(url: str, expect_sha256: str | None = None) -> dict:
    out = {"url": url, "checked_at": utc_now()}
    try:
        r = requests.get(url, headers=UA, timeout=45, allow_redirects=True)
    except requests.RequestException as exc:
        out.update(http_status=None, error=type(exc).__name__)
        return out
    out.update(http_status=r.status_code, content_type=r.headers.get("content-type"))
    if r.url != url:
        out["final_url"] = r.url
    if expect_sha256 is not None and r.status_code == 200:
        out["sha256"] = sha256_bytes(r.content)
        out["sha256_matches"] = out["sha256"] == expect_sha256
    return out


def _commit_of_tag(slug: str, tag: str) -> str | None:
    ref, _ = gh_api(f"repos/{slug}/git/ref/tags/{tag}")
    if not ref:
        return None
    obj = ref["object"]
    if obj["type"] == "tag":
        tobj, _ = gh_api(f"repos/{slug}/git/tags/{obj['sha']}")
        return tobj["object"]["sha"] if tobj else None
    return obj["sha"]


def probe_release(note: Note) -> dict:
    slug = note.repo_slug
    expected = parse_sums(note.sums_path)
    expected[note.sums_path.name] = sha256_file(note.sums_path)
    rel, err = gh_api(f"repos/{slug}/releases/tags/{note.tag}")
    if not rel:
        return {"tag": note.tag, "exists": False, "error": err}
    assets = []
    for a in rel.get("assets", []):
        r = requests.get(a["browser_download_url"], headers=UA, timeout=90)
        digest = sha256_bytes(r.content) if r.status_code == 200 else None
        assets.append({"name": a["name"], "size": a["size"], "download_status": r.status_code, "sha256": digest,
                       "github_digest": a.get("digest"), "matches_sha256sums": digest == expected.get(a["name"])})
    names = {a["name"] for a in assets}
    return {
        "tag": note.tag,
        "exists": True,
        "id": rel["id"],
        "url": rel["html_url"],
        "name": rel.get("name"),
        "draft": rel.get("draft"),
        "immutable": rel.get("immutable"),
        "published_at": rel.get("published_at"),
        "target_commit": _commit_of_tag(slug, note.tag),
        "assets": assets,
        "all_assets_present_and_matching": names == set(expected) and all(a["matches_sha256sums"] for a in assets),
    }


def probe_pages(note: Note, pdf_sha: str) -> dict:
    slug = note.repo_slug
    pages, err = gh_api(f"repos/{slug}/pages")
    deps, _ = gh_api(f"repos/{slug}/deployments?environment=github-pages&per_page=1")
    dep = deps[0] if deps else None
    state = None
    if dep:
        statuses, _ = gh_api(f"repos/{slug}/deployments/{dep['id']}/statuses?per_page=1")
        state = statuses[0]["state"] if statuses else None
    pdf_url = f"{note.preview_url}v{note.version}/{note.pdf_path.name}"
    page = http_probe(note.preview_url)
    pdf = http_probe(pdf_url, pdf_sha)
    return {
        "url": note.preview_url,
        "pages_site": pages.get("html_url") if pages else None,
        "pages_status": pages.get("status") if pages else None,
        "pages_error": err,
        "deployment_id": dep["id"] if dep else None,
        "deployment_commit": dep["sha"] if dep else None,
        "deployment_state": state,
        "page": page,
        "pdf": pdf,
        "verified": page.get("http_status") == 200 and bool(pdf.get("sha256_matches")),
    }


def probe_canonical(note: Note, pdf_sha: str) -> dict:
    page = http_probe(note.canonical_url)
    pdf = http_probe(note.pdf_url, pdf_sha)
    live = page.get("http_status") == 200 and bool(pdf.get("sha256_matches"))
    return {"url": note.canonical_url, "status": "LIVE" if live else "NOT_DEPLOYED", "page": page, "pdf": pdf}


def probe_zenodo(note: Note) -> dict:
    rec = note.zenodo_record()
    if not rec:
        return {"status": "NOT_STARTED", "record_id": None, "doi": None,
                "reason": "no deposition has been created (ZENODO_ACCESS_TOKEN not provided)"}
    out = {"status": rec.get("state", "unknown").upper(), "environment": rec.get("environment"),
           "deposition_id": rec.get("deposition_id"), "record_id": rec.get("record_id"),
           "reserved_doi": rec.get("reserved_doi"), "doi": None}
    if rec.get("state") == "published" and rec.get("record_id"):
        r = requests.get(f"{ZENODO_PUBLIC[rec['environment']]}{rec['record_id']}", headers=UA, timeout=45)
        out["public_api_status"] = r.status_code
        if r.status_code == 200:
            data = r.json()
            out["doi"] = data.get("doi") or data.get("pids", {}).get("doi", {}).get("identifier")
            out["record_url"] = data.get("links", {}).get("self_html") or data.get("links", {}).get("html")
            local = {f["filename"]: f["md5"] for f in rec.get("files", [])}
            remote = {f.get("key"): str(f.get("checksum", "")).removeprefix("md5:")
                      for f in (data.get("files") or [])}
            out["files_match"] = bool(remote) and remote == local
    return out


def generate(note: Note, validations: list[Result]) -> dict:
    sums = parse_sums(note.sums_path)
    pdf_sha = sums[note.pdf_path.name]
    repo, repo_err = gh_api(f"repos/{note.repo_slug}")
    immutable, _ = gh_api(f"repos/{note.repo_slug}/immutable-releases")
    release = probe_release(note)
    preview = probe_pages(note, pdf_sha)
    canonical = probe_canonical(note, pdf_sha)
    zen = probe_zenodo(note)

    blockers = []
    if canonical["status"] != "LIVE":
        blockers.append({"item": "canonical_website", "state": canonical["status"],
                         "http_status": canonical["page"].get("http_status"),
                         "cause": "The research pages are not yet deployed to the canonical host."})
    if zen["status"] != "PUBLISHED":
        blockers.append({"item": "zenodo_doi", "state": zen["status"],
                         "cause": "No Zenodo access token has been provided." if zen["status"] == "NOT_STARTED"
                         else "The Zenodo draft has not been published."})
    if not note.license_granted:
        blockers.append({"item": "license", "state": "PENDING",
                         "cause": "No license has been granted for the note text; an open-access archive record "
                                  "requires one."})
    fails = [v for v in validations if v.status == "FAIL"]
    complete = (not blockers and not fails and release.get("all_assets_present_and_matching")
                and preview["verified"])
    return {
        "receipt_type": "margelis-research/publication-receipt/1",
        "generated_at": utc_now(),
        "generated_by": f"python tools/publish.py receipt {note.number}",
        "note": note.number,
        "version": note.version,
        "title": note.full_title,
        "status": "COMPLETE" if complete else "PARTIAL",
        "repository": {"url": note.repo_url, "exists": bool(repo),
                       "visibility": repo.get("visibility") if repo else None,
                       "default_branch": repo.get("default_branch") if repo else None,
                       "immutable_releases_enabled": (immutable or {}).get("enabled"),
                       "error": repo_err},
        "commit_sha": release.get("target_commit"),
        "release": release,
        "canonical_website": canonical,
        "preview_website": preview,
        "hashes": {"pdf_sha256": pdf_sha, "markdown_sha256": sums[note.md_path.name],
                   "metadata_sha256": sums[note.metadata_path.name],
                   "sha256sums_sha256": sha256_file(note.sums_path)},
        "zenodo": zen,
        "doi": zen.get("doi"),
        "publication_timestamp": release.get("published_at"),
        "license": {"status": note.license["status"], "spdx": note.license.get("spdx"),
                    "proposed": note.license.get("proposed")},
        "validation": {
            "summary": {s: sum(1 for v in validations if v.status == s) for s in ("PASS", "FAIL", "WARN", "SKIP")},
            "results": [v.as_dict() for v in validations],
        },
        "blockers": blockers,
    }


def write(note: Note, validations: list[Result]) -> dict:
    data = generate(note, validations)
    write_json(note.receipt_path, data)
    return data
