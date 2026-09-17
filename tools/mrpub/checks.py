"""Pre-publication checks. Checks read files and (optionally) the network; they never write.

Every check returns Result(id, status, detail) with status PASS, FAIL, WARN or SKIP.
"""
from __future__ import annotations

import copy
import html
import json
import os
import re
import tempfile
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

import jsonschema
import requests
import yaml
from pypdf import PdfReader

from . import citation, mdparse, secretscan, zenodo
from .common import (BENCHMARK, ROOT, SCHEMAS, SITE, Note, PipelineError, all_notes,
                     canonical_license_check, git, human_date, license_display_html,
                     load_json, load_note, load_yaml, parse_sums, sha256_file, strip_number)

PASS, FAIL, WARN, SKIP = "PASS", "FAIL", "WARN", "SKIP"
UA = {"User-Agent": "margelis-research-publication-check/1 (+https://github.com/M12-pixel1/margelis-research)"}
CACHE = ROOT / ".cache"
EXPECTED_SCENARIOS = {
    "expired_mandate", "policy_drift", "model_swap", "replay", "subagent_scope_expansion",
    "memory_as_authority", "indirect_execution", "false_done", "partial_external_success", "credential_drift",
}


@dataclass
class Result:
    id: str
    status: str
    detail: str = ""

    def as_dict(self) -> dict:
        return {"id": self.id, "status": self.status, "detail": self.detail}


def norm(text: str) -> str:
    return " ".join(str(text).split())


def validator(schema: dict) -> jsonschema.Draft202012Validator:
    return jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())


def schema_errors(schema: dict, instance) -> list[str]:
    return [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}"
            for e in sorted(validator(schema).iter_errors(instance), key=lambda e: list(e.absolute_path))]


def fetch_ok(url: str) -> tuple[bool, str]:
    last = ""
    for _ in range(2):
        try:
            r = requests.get(url, headers=UA, timeout=30, allow_redirects=True)
            if r.status_code == 200:
                return True, f"200 {r.url}" if r.url != url else "200"
            last = f"HTTP {r.status_code}"
        except requests.RequestException as exc:
            last = type(exc).__name__
    return False, last


class _Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, list[str]] = {}
        self.links: list[tuple[str, str]] = []
        self.refs: list[str] = []
        self.ids: set[str] = set()
        self.scripts: list[tuple[str, str]] = []
        self.title = ""
        self._in_script = None
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            self.ids.add(a["id"])
        if tag == "meta":
            key = a.get("name") or a.get("property")
            if key:
                self.meta.setdefault(key, []).append(a.get("content", ""))
        elif tag == "link":
            self.links.append((a.get("rel", ""), a.get("href", "")))
        elif tag == "a" and "href" in a:
            self.refs.append(a["href"])
        elif tag in ("img", "source") and "src" in a:
            self.refs.append(a["src"])
        elif tag == "script":
            self._in_script = [a.get("type", ""), ""]
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag == "script" and self._in_script is not None:
            self.scripts.append(tuple(self._in_script))
            self._in_script = None
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_script is not None:
            self._in_script[1] += data
        if self._in_title:
            self.title += data


def parse_page(path: Path) -> _Page:
    p = _Page()
    p.feed(path.read_text(encoding="utf-8"))
    return p


# =========================================================================== note checks
class NoteChecks:
    def __init__(self, note: Note, online: bool = False):
        self.note = note
        self.online = online
        self.text = note.md_path.read_text(encoding="utf-8")
        self.tokens = mdparse.parse(self.text)
        self.title_tokens, self.body_tokens = mdparse.split_title_block(self.tokens)
        self.sections = mdparse.sections(self.body_tokens)
        self.md_links = [u for u in mdparse.links(self.tokens) if u.startswith("http")]

    def run(self, built: bool = True) -> list[Result]:
        names = ["input_schema", "markdown_syntax", "markdown_structure", "title_block", "locked_statements",
                 "references_cited", "github_render", "external_links"]
        if built:
            names += ["sha256sums", "metadata_schema", "metadata_consistency", "pdf_opens", "pdf_fonts_embedded",
                      "pdf_text", "pdf_links", "citation_cff_schema", "citation_cff_consistency", "site_page",
                      "zenodo_metadata", "license_consistency", "versioning", "published_claims", "name_spelling"]
        results = []
        for name in names:
            cid = f"note{self.note.number}.{name}"
            try:
                status, detail = getattr(self, f"c_{name}")()
            except Exception as exc:  # a crashing check is a failing check
                status, detail = FAIL, f"{type(exc).__name__}: {exc}"
            results.append(Result(cid, status, detail))
        return results

    # ---------------------------------------------------------------- inputs
    def c_input_schema(self):
        errs = schema_errors(load_json(SCHEMAS / "note-input.schema.json"), citation.as_json_compatible(self.note.meta))
        return (FAIL, "; ".join(errs)) if errs else (PASS, "note.yaml valid")

    def c_markdown_syntax(self):
        bad = mdparse.unsupported_tokens(self.tokens)
        return (FAIL, f"unsupported elements: {bad}") if bad else (PASS, "only supported CommonMark + table elements")

    def c_markdown_structure(self):
        problems = []
        h1 = mdparse.headings(self.tokens, 1)
        if len(h1) != 1:
            problems.append(f"expected one H1, found {len(h1)}")
        h2 = mdparse.headings(self.body_tokens, 2)
        numbered = [h for h in h2 if re.match(r"^\d+\.\s", h)]
        nums = [int(h.split(".")[0]) for h in numbered]
        if nums != list(range(1, len(nums) + 1)):
            problems.append(f"section numbers not sequential: {nums}")
        if h2[:len(numbered)] != numbered:
            problems.append("unnumbered sections must follow the numbered ones")
        for req in self.note.series["required_sections"]:
            if req not in {strip_number(h) for h in h2}:
                problems.append(f"missing required section '{req}'")
        tables = [t for t in self.body_tokens if t.type == "table_open"]
        if not tables:
            problems.append("adversarial test-set table not found")
        return (FAIL, "; ".join(problems)) if problems else \
            (PASS, f"1 H1, {len(numbered)} numbered sections + {len(h2) - len(numbered)} end section(s), {len(tables)} table(s)")

    def c_title_block(self):
        text = norm(mdparse.plain_text(self.title_tokens))
        n = self.note
        a = n.authors[0]
        required = [n.series_name.upper(), n.title, n.subtitle, f"{a['given_name']} {a['family_name']}",
                    a["affiliation"], n.label]
        missing = [r for r in required if norm(r) not in text]
        return (FAIL, f"title block lacks: {missing}") if missing else \
            (PASS, "series, title, subtitle, author, affiliation, number, version and date match note.yaml")

    def c_locked_statements(self):
        missing = []
        whole = norm(mdparse.plain_text(self.tokens))
        for section, statements in (self.note.meta.get("locked_statements") or {}).items():
            haystack = norm(self.sections[section]) if section in self.sections else whole
            for s in statements:
                if norm(s) not in haystack:
                    missing.append(f"[{section}] {s[:50]}")
        count = sum(len(v) for v in (self.note.meta.get("locked_statements") or {}).values())
        return (FAIL, f"missing: {missing}") if missing else (PASS, f"{count} locked statements present verbatim")

    def c_references_cited(self):
        refs = load_json(self.note.references_path)["references"]
        allowed = {r["url"] for r in refs} | {u for r in refs for u in r.get("related_urls", [])}
        not_cited = [r["url"] for r in refs if r["url"] not in self.md_links]
        unlisted = [u for u in self.md_links if u not in allowed]
        problems = []
        if not_cited:
            problems.append(f"in references.json but not in the note: {not_cited}")
        if unlisted:
            problems.append(f"linked in the note but not in references.json: {unlisted}")
        return (FAIL, "; ".join(problems)) if problems else (PASS, f"{len(refs)} references, all cited and listed")

    def c_github_render(self):
        if not self.online:
            return SKIP, "offline"
        headers = dict(UA)
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        r = requests.post("https://api.github.com/markdown", headers=headers,
                          json={"text": self.text, "mode": "gfm"}, timeout=60)
        if r.status_code != 200:
            return WARN, f"GitHub Markdown API HTTP {r.status_code}"
        out = r.text
        h2_expected = len(mdparse.headings(self.body_tokens, 2))
        h2_found = len(re.findall(r"<h2[ >]", out))
        rows_expected = sum(1 for t in self.body_tokens if t.type == "tr_open")
        rows_found = len(re.findall(r"<tr[ >]", out))
        tables = len(re.findall(r"<table[ >]", out))
        ok = tables >= 1 and rows_found == rows_expected and h2_found == h2_expected and out.count("<h1") == 1
        return (PASS if ok else FAIL), (f"GitHub renders tables={tables}, rows={rows_found}/{rows_expected}, "
                                        f"h2={h2_found}/{h2_expected}")

    def c_external_links(self):
        if not self.online:
            return SKIP, "offline"
        refs = load_json(self.note.references_path)["references"]
        urls = sorted(set(self.md_links) | {r["url"] for r in refs}
                      | {u for r in refs for u in r.get("related_urls", [])})
        bad = []
        for u in urls:
            ok, info = fetch_ok(u)
            if not ok:
                bad.append(f"{u} ({info})")
        return (FAIL, f"unreachable: {bad}") if bad else (PASS, f"{len(urls)} external URLs return HTTP 200")

    # ---------------------------------------------------------------- built artifacts
    def c_sha256sums(self):
        n = self.note
        sums = parse_sums(n.sums_path)
        expected = {n.md_path.name, n.pdf_path.name, n.metadata_path.name}
        if set(sums) != expected:
            return FAIL, f"SHA256SUMS lists {sorted(sums)}, expected {sorted(expected)}"
        bad = [name for name, digest in sums.items() if sha256_file(n.dir / name) != digest]
        return (FAIL, f"digest mismatch: {bad}") if bad else (PASS, "PDF, Markdown and metadata.json match SHA256SUMS")

    def c_metadata_schema(self):
        errs = schema_errors(load_json(SCHEMAS / "note-metadata.schema.json"), load_json(self.note.metadata_path))
        return (FAIL, "; ".join(errs)) if errs else (PASS, "metadata.json valid")

    def c_metadata_consistency(self):
        from .build import build_metadata  # local import: build imports checks-free modules only
        n = self.note
        current = load_json(n.metadata_path)
        expected = build_metadata(n, pdf_pages=current["files"][1].get("pages"))
        released = bool(git("tag", "-l", n.tag, check=False))
        # A released manifest records the license status at release time; later grants live elsewhere.
        diffs = [k for k in expected if expected[k] != current.get(k) and not (released and k == "license")]
        if released and expected["license"] != current["license"] and current["license"]["status"] != "pending":
            diffs.append("license")
        return (FAIL, f"metadata.json differs from note.yaml/files in: {diffs}") if diffs else \
            (PASS, "metadata.json matches note.yaml, references.json and file digests"
             + (" (license as recorded at release)" if released and expected["license"] != current["license"] else ""))

    def _pdf(self) -> PdfReader:
        return PdfReader(str(self.note.pdf_path))

    def c_pdf_opens(self):
        r = self._pdf()
        info = r.metadata or {}
        problems = []
        if info.get("/Title") != self.note.full_title:
            problems.append(f"/Title={info.get('/Title')!r}")
        if info.get("/Author") != ", ".join(self.note.author_names):
            problems.append(f"/Author={info.get('/Author')!r}")
        if r.is_encrypted:
            problems.append("encrypted")
        return (FAIL, "; ".join(problems)) if problems else \
            (PASS, f"{len(r.pages)} pages, PDF {r.pdf_header[-3:]}, title and author set")

    def c_pdf_fonts_embedded(self):
        r = self._pdf()
        missing, names = set(), set()
        for page in r.pages:
            fonts = (page.get("/Resources") or {}).get_object().get("/Font") or {}
            for ref in fonts.get_object().values():
                f = ref.get_object()
                base = str(f.get("/BaseFont"))
                names.add(base)
                sub = f.get("/Subtype")
                if sub == "/Type3":
                    continue
                if sub == "/Type0":
                    f = f["/DescendantFonts"][0].get_object()
                desc = f.get("/FontDescriptor")
                desc = desc.get_object() if desc is not None else {}
                if not any(k in desc for k in ("/FontFile", "/FontFile2", "/FontFile3")):
                    missing.add(base)
        return (FAIL, f"not embedded: {sorted(missing)}") if missing else \
            (PASS, f"all {len(names)} fonts embedded: {', '.join(sorted(n.split('+')[-1] for n in names))}")

    def c_pdf_text(self):
        text = norm(" ".join(p.extract_text() or "" for p in self._pdf().pages))
        n = self.note
        needles = [n.title, n.subtitle, *n.author_names, n.authors[0]["affiliation"], n.label]
        needles += mdparse.headings(self.body_tokens, 2)
        for statements in (n.meta.get("locked_statements") or {}).values():
            needles += statements
        missing = [x for x in needles if norm(x) not in text]
        return (FAIL, f"not found in PDF text: {missing}") if missing else \
            (PASS, f"{len(needles)} title, section and locked-statement strings found in PDF text")

    def c_pdf_links(self):
        uris = set()
        for page in self._pdf().pages:
            for annot in page.get("/Annots") or []:
                a = annot.get_object().get("/A")
                if a is not None and a.get_object().get("/URI"):
                    uris.add(str(a.get_object()["/URI"]))
        md = set(self.md_links)
        return (PASS, f"{len(uris)} link annotations, identical to the Markdown links") if uris == md else \
            (FAIL, f"PDF-only: {sorted(uris - md)}; Markdown-only: {sorted(md - uris)}")

    def _cff(self) -> dict:
        return yaml.safe_load((ROOT / "CITATION.cff").read_text(encoding="utf-8"))

    def c_citation_cff_schema(self):
        cached = CACHE / "cff-1.2.0-schema.json"
        if not cached.exists():
            if not self.online:
                return SKIP, "offline and CFF schema not cached"
            r = requests.get(citation.CFF_SCHEMA_URL, headers=UA, timeout=30)
            r.raise_for_status()
            cached.parent.mkdir(exist_ok=True)
            cached.write_text(r.text, encoding="utf-8")
        schema = json.loads(cached.read_text(encoding="utf-8"))
        errs = [f"{'/'.join(map(str, e.absolute_path))}: {e.message}" for e in
                jsonschema.Draft7Validator(schema).iter_errors(citation.as_json_compatible(self._cff()))]
        return (FAIL, "; ".join(errs[:5])) if errs else (PASS, "CITATION.cff valid against CFF 1.2.0 schema")

    def c_citation_cff_consistency(self):
        latest = max(all_notes())
        if self.note.number != latest:
            return SKIP, f"preferred citation is note {latest}"
        cff = self._cff()
        expected = citation.as_json_compatible(citation.build([load_note(x) for x in all_notes()]))
        actual = citation.as_json_compatible(cff)
        diffs = [k for k in set(expected) | set(actual) if expected.get(k) != actual.get(k)]
        return (FAIL, f"CITATION.cff out of date in: {sorted(diffs)} (run build)") if diffs else \
            (PASS, "CITATION.cff title, version, date, authors, URLs and DOI/license state match the note")

    def c_site_page(self):
        n = self.note
        page_path = n.site_dir / "index.html"
        p = parse_page(page_path)
        m = lambda k: (p.meta.get(k) or [None])[0]  # noqa: E731
        problems = []
        canon = [h for rel, h in p.links if rel == "canonical"]
        expect = {
            "canonical": (canon[0] if canon else None, n.canonical_url),
            "og:url": (m("og:url"), n.canonical_url),
            "og:title": (m("og:title"), n.full_title),
            "description": (norm(m("description") or ""), norm(n.meta["abstract"])),
            "citation_title": (m("citation_title"), n.full_title),
            "citation_author": (m("citation_author"),
                                f"{n.authors[0]['family_name']}, {n.authors[0]['given_name']}"),
            "citation_author_institution": (m("citation_author_institution"), n.authors[0]["affiliation"]),
            "citation_publication_date": (m("citation_publication_date"), n.date.replace("-", "/")),
            "citation_pdf_url": (m("citation_pdf_url"), n.pdf_url),
            "article:published_time": (m("article:published_time"), n.date),
            "og:image": (m("og:image"), f"{n.canonical_url}{n.og_image_name}"),
        }
        for key, (got, want) in expect.items():
            if got != want:
                problems.append(f"{key}: {got!r} != {want!r}")
        doi = n.doi()
        if (m("citation_doi") or None) != doi:
            problems.append(f"citation_doi {m('citation_doi')!r} != {doi!r}")
        if n.title not in p.title:
            problems.append("<title> lacks the note title")
        scripts = [t for t, _ in p.scripts]
        if any(t != "application/ld+json" for t in scripts):
            problems.append(f"executable script present ({scripts}); host CSP is script-src 'none'")
        ld = json.loads(p.scripts[0][1]) if p.scripts else {}
        pdf_sha = parse_sums(n.sums_path)[n.pdf_path.name]
        for key, want in {"name": n.full_title, "datePublished": n.date, "version": n.version,
                          "creativeWorkStatus": n.meta["status"]}.items():
            if ld.get(key) != want:
                problems.append(f"JSON-LD {key}: {ld.get(key)!r}")
        if ld.get("author", [{}])[0].get("name") != n.author_names[0] or \
                ld["author"][0].get("affiliation", {}).get("name") != n.authors[0]["affiliation"]:
            problems.append("JSON-LD author/affiliation mismatch")
        if ld.get("encoding", [{}])[0].get("sha256") != pdf_sha:
            problems.append("JSON-LD PDF sha256 mismatch")
        external = [h for rel, h in p.links if rel in ("stylesheet", "preload", "icon") and h.startswith("http")]
        if external:
            problems.append(f"external resources: {external}")
        body = page_path.read_text(encoding="utf-8")
        for needle in ("What remains unproven", n.meta["status"], html.escape(n.label, quote=True)):
            if needle not in body:
                problems.append(f"page lacks {needle!r}")
        sums = parse_sums(n.sums_path)
        vdir = n.site_version_dir
        for name, digest in sums.items():
            f = vdir / name
            if not f.exists() or sha256_file(f) != digest:
                problems.append(f"{f.relative_to(ROOT)} missing or differs from SHA256SUMS")
            if digest not in body:
                problems.append(f"integrity table lacks digest of {name}")
        if not (vdir / "SHA256SUMS").exists() or sha256_file(vdir / "SHA256SUMS") != sha256_file(n.sums_path):
            problems.append("site SHA256SUMS differs from research SHA256SUMS")
        og = n.site_dir / n.og_image_name
        if not og.exists():
            problems.append("OpenGraph image missing")
        else:
            from PIL import Image
            with Image.open(og) as im:
                if im.size != (1200, 630):
                    problems.append(f"OpenGraph image is {im.size}")
        return (FAIL, "; ".join(problems)) if problems else \
            (PASS, "canonical, OpenGraph, citation_* and JSON-LD match the note; no scripts; versioned files match SHA256SUMS")

    def c_zenodo_metadata(self):
        n = self.note
        meta = zenodo.build_metadata(n)
        problems = []
        want = {"title": n.full_title, "publication_date": n.date, "version": n.version,
                "keywords": n.meta["keywords"], "upload_type": "publication",
                "publication_type": n.meta["zenodo"]["publication_type"]}
        for k, v in want.items():
            if meta.get(k) != v:
                problems.append(f"{k}: {meta.get(k)!r}")
        if [c["name"] for c in meta["creators"]] != [f"{a['family_name']}, {a['given_name']}" for a in n.authors]:
            problems.append("creators")
        if norm(n.meta["abstract"]) not in meta["description"]:
            problems.append("description lacks the abstract")
        if n.license_granted:
            if meta.get("access_right") != "open" or meta.get("license") != n.license["spdx"].lower():
                problems.append("license/access_right")
        elif meta.get("access_right") != "closed" or "license" in meta:
            problems.append("license pending but payload would open the record or set a license")
        rec = n.zenodo_record()
        detail = "payload matches note metadata"
        if rec:
            local = {f.name: sha256_file(f) for f in zenodo.upload_files(n)}
            if {f["filename"]: f["sha256"] for f in rec.get("files", [])} != local:
                problems.append("zenodo.json files differ from local files")
            if not rec.get("metadata_matches"):
                problems.append("last Zenodo verification reported a metadata mismatch")
            detail += f"; Zenodo {rec.get('environment')} deposition {rec.get('deposition_id')} state={rec.get('state')}"
        else:
            detail += "; no Zenodo deposition yet"
        return (FAIL, "; ".join(problems)) if problems else (PASS, detail)

    def c_license_consistency(self):
        n = self.note
        lic_file = (ROOT / "LICENSE").read_text(encoding="utf-8")
        cff = self._cff()
        meta = load_json(n.metadata_path)["license"]
        page = (n.site_dir / "index.html").read_text(encoding="utf-8")
        problems = []
        if n.license_granted:
            spdx = n.license["spdx"]
            if spdx not in lic_file:
                problems.append("LICENSE does not name the granted license")
            if cff.get("license") != spdx:
                problems.append("CITATION.cff license missing")
            released_before_grant = bool(git("tag", "-l", n.tag, check=False)) and meta.get("status") == "pending"
            if meta.get("spdx") != spdx and not released_before_grant:
                problems.append("metadata.json license missing")
            if spdx not in page:
                problems.append("web page does not show the granted license")
        else:
            if "No license has been granted" not in lic_file:
                problems.append("LICENSE does not state that no license is granted")
            if "license" in cff or "license" in cff.get("preferred-citation", {}):
                problems.append("CITATION.cff declares a license while the decision is pending")
            if meta.get("spdx") is not None or meta.get("status") != "pending":
                problems.append("metadata.json declares a license while pending")
            if "Not yet granted" not in page:
                problems.append("web page does not say the license is pending")
        state = f"granted ({n.license['spdx']})" if n.license_granted else "pending"
        return (FAIL, "; ".join(problems)) if problems else (PASS, f"license {state} consistently in all files")

    def _earlier_versions_intact(self) -> list[str]:
        """Every earlier version must be released and still served byte-identically under site/.../v<x>/."""
        n = self.note
        problems = []
        for v in n.previous_versions():
            tag = f"research-note-{n.number}-v{v}"
            released = git("show", f"{tag}:research/{n.number}/SHA256SUMS", check=False)
            if not released:
                problems.append(f"earlier version {v}: tag {tag} missing locally")
                continue
            vdir = n.site_dir / f"v{v}"
            for line in released.splitlines():
                if not line.strip():
                    continue
                digest, name = line.split(maxsplit=1)
                f = vdir / name.strip()
                if not f.exists() or sha256_file(f) != digest:
                    problems.append(f"earlier version {v}: {f.relative_to(ROOT).as_posix()} missing or changed")
            if not (vdir / "SHA256SUMS").exists() or \
                    (vdir / "SHA256SUMS").read_text(encoding="utf-8").strip() != released.strip():
                problems.append(f"earlier version {v}: site SHA256SUMS differs from {tag}")
        return problems

    def c_versioning(self):
        n = self.note
        tag = n.tag
        earlier = self._earlier_versions_intact()
        if earlier:
            return FAIL, "; ".join(earlier)
        kept = f"; earlier versions {', '.join(n.previous_versions())} intact" if n.previous_versions() else ""
        local = git("tag", "-l", tag, check=False)
        remote = ""
        if self.online:
            remote = git("ls-remote", "--tags", "origin", f"refs/tags/{tag}", check=False)
        if not local and not remote:
            return PASS, f"{tag} not released yet; artifacts may still change{kept}"
        if not local:
            return FAIL, f"{tag} exists on origin but not locally; run `git fetch --tags` and re-check"
        released = git("show", f"{tag}:research/{n.number}/SHA256SUMS", check=False)
        current = n.sums_path.read_text(encoding="utf-8").strip()
        changed = [name for name, digest in parse_sums(n.sums_path).items()
                   if sha256_file(n.dir / name) != digest]
        released_digests = {}
        for line in released.splitlines():
            if line.strip():
                digest, name = line.split(maxsplit=1)
                released_digests[name.strip()] = digest
        changed += [name for name, digest in released_digests.items()
                    if not (n.dir / name).exists() or sha256_file(n.dir / name) != digest]
        if released.strip() != current or changed:
            return FAIL, (f"{tag} is released and the working tree differs from it ({sorted(set(changed)) or 'SHA256SUMS'}). "
                          f"Published versions are never overwritten: add a new version to note.yaml.")
        return PASS, f"{tag} released; working-tree files are byte-identical to the released digests{kept}"

    def _published_files(self) -> list[Path]:
        n = self.note
        files = [n.md_path, n.metadata_path, n.site_dir / "index.html", SITE / "research" / "index.html",
                 ROOT / "README.md", n.dir / "README.md", ROOT / "CITATION.cff", ROOT / "SECURITY.md",
                 ROOT / "LICENSE"]
        files += sorted(BENCHMARK.rglob("*.md")) + sorted(BENCHMARK.rglob("*.yaml"))
        return [f for f in files if f.exists()]

    def c_published_claims(self):
        pats = [re.compile(p, re.IGNORECASE) for p in self.note.series["forbidden_claims"]]
        allowed = [a.lower() for a in self.note.series.get("allowed_claim_contexts", [])]
        hits = []
        for f in self._published_files():
            text = f.read_text(encoding="utf-8")
            low = norm(text).lower()
            for pat in pats:
                for mt in pat.finditer(low):
                    window = low[max(0, mt.start() - 60): mt.end() + 60]
                    if not any(a in window for a in allowed):
                        hits.append(f"{f.relative_to(ROOT).as_posix()}: '{mt.group(0)}'")
        return (FAIL, f"unsupported claim language: {hits}") if hits else \
            (PASS, f"no novelty/marketing language in {len(self._published_files())} published files")

    def c_name_spelling(self):
        hits = []
        for f in self._published_files():
            text = f.read_text(encoding="utf-8")
            for entry in self.note.series["names"]:
                for v in entry["variants"]:
                    if v in text:
                        hits.append(f"{f.relative_to(ROOT).as_posix()}: '{v}' (use '{entry['canonical']}')")
        n = self.note
        page = (n.site_dir / "index.html").read_text(encoding="utf-8")
        for canonical in (n.author_names[0], n.authors[0]["affiliation"], n.series_name):
            for f in (n.md_path, n.site_dir / "index.html"):
                if canonical not in f.read_text(encoding="utf-8"):
                    hits.append(f"{f.name} lacks '{canonical}'")
        if human_date(n.date) not in page or human_date(n.date) not in self.text:
            hits.append("publication date not consistent between page and note")
        return (FAIL, "; ".join(hits)) if hits else (PASS, "author, organization, series and date spelled consistently")


# =========================================================================== repository checks
def check_license_display_contract() -> Result:
    """Pin the shared License-row renderer/parser contract for granted and pending states."""
    granted = {
        "status": "granted", "spdx": "CC-BY-4.0",
        "authorized_by": "Test Principal", "authorized_on": "2026-09-17",
    }
    pending = {
        "status": "pending", "spdx": None,
        "authorized_by": None, "authorized_on": None,
    }

    def page(meta: dict) -> str:
        return f"<dl><dt>License</dt><dd>{license_display_html(meta)}</dd></dl>"

    problems = []
    for label, meta in (("granted", granted), ("pending", pending)):
        result = canonical_license_check(page(meta), meta)
        if not result["matches"]:
            problems.append(f"{label} round-trip mismatch: {result}")

    if canonical_license_check(page(granted), pending)["matches"]:
        problems.append("granted HTML incorrectly accepted as pending")
    if canonical_license_check(page(pending), granted)["matches"]:
        problems.append("pending HTML incorrectly accepted as granted")

    missing = canonical_license_check("<html><body>No license row</body></html>", granted)
    if missing["matches"] or missing["observed"] is not None:
        problems.append(f"missing License row not rejected: {missing}")

    return Result("repo.license_display_contract", FAIL if problems else PASS,
                  "; ".join(problems) if problems else
                  "granted/pending render+parse round-trips pass; cross-state and missing-row cases rejected")


def check_benchmark() -> list[Result]:
    out = []
    root = BENCHMARK / "v0.2"
    schema = load_json(root / "schemas" / "scenario.schema.json")
    note_cases = set()
    try:
        note = load_note("001")
        tokens = mdparse.parse(note.md_path.read_text(encoding="utf-8"))
        rows, in_body, cell_idx = [], False, 0
        for i, t in enumerate(tokens):
            if t.type == "tbody_open":
                in_body = True
            elif t.type == "tbody_close":
                in_body = False
            elif in_body and t.type == "tr_open":
                cell_idx = 0
            elif in_body and t.type == "td_open":
                if cell_idx == 0:
                    rows.append(mdparse.inline_text(tokens[i + 1]))
                cell_idx += 1
        note_cases = set(rows)
    except PipelineError:
        pass
    problems, ids, cases = [], set(), set()
    files = sorted((root / "scenarios").glob("*.yaml"))
    for f in files:
        data = load_yaml(f)
        for e in schema_errors(schema, data):
            problems.append(f"{f.name}: {e}")
        if data.get("id") != f.stem:
            problems.append(f"{f.name}: id {data.get('id')!r} != file name")
        if data.get("id") in ids:
            problems.append(f"duplicate id {data.get('id')}")
        ids.add(data.get("id"))
        cases.add(data.get("note_case"))
    if ids != EXPECTED_SCENARIOS:
        problems.append(f"scenario set differs: missing {sorted(EXPECTED_SCENARIOS - ids)}, extra {sorted(ids - EXPECTED_SCENARIOS)}")
    if note_cases and cases != note_cases:
        problems.append(f"note cases not covered one-to-one: note-only {sorted(note_cases - cases)}, "
                        f"scenario-only {sorted(cases - note_cases)}")
    out.append(Result("benchmark.scenarios", FAIL if problems else PASS,
                      "; ".join(problems) if problems else f"{len(files)} scenarios valid; one per Research Note 001 case"))

    rschema = load_json(root / "schemas" / "receipt.schema.json")
    problems = []
    examples = sorted((root / "schemas" / "examples").glob("*.json"))
    for f in examples:
        problems += [f"{f.name}: {e}" for e in schema_errors(rschema, load_json(f))]
    # paired negative tests: the conditional rules must reject these mutations
    base = load_json(root / "schemas" / "examples" / "receipt.synthetic-example.unverified.json")
    negatives = {}
    m1 = copy.deepcopy(base); m1["outcome_status"] = "VERIFIED_SUCCESS"; m1["verification_source"] = None
    negatives["verified success without verification source"] = m1
    m2 = copy.deepcopy(base); m2["authorization_decision"] = "DENY"
    negatives["denied action with an executed action"] = m2
    m3 = copy.deepcopy(base); m3["outcome_status"] = "DONE"
    negatives["unknown outcome status"] = m3
    m4 = copy.deepcopy(base); m4["evidence_hashes"] = ["md5:abc"]
    negatives["non-SHA-256 evidence digest"] = m4
    for label, inst in negatives.items():
        if not schema_errors(rschema, inst):
            problems.append(f"schema accepted an invalid receipt: {label}")
    out.append(Result("benchmark.receipt_schema", FAIL if problems else PASS,
                      "; ".join(problems) if problems else
                      f"{len(examples)} synthetic examples valid; {len(negatives)} invalid mutations rejected"))

    from .benchmark_results import validate_results_dir
    from .benchmark_results_selftest import run_selftest
    selftest_ok, selftest_detail = run_selftest(root)
    out.append(Result("benchmark.result_bundle_validator_selftest", PASS if selftest_ok else FAIL, selftest_detail))
    results_ok, results_detail = validate_results_dir(root)
    out.append(Result("benchmark.result_bundles", PASS if results_ok else FAIL, results_detail))
    return out


def check_internal_links() -> Result:
    problems, count = [], 0
    for page in sorted(SITE.rglob("*.html")):
        p = parse_page(page)
        for ref in p.refs + [h for rel, h in p.links if rel not in ("canonical",)]:
            if re.match(r"^[a-z]+:", ref) or ref.startswith("//"):
                continue
            count += 1
            path, _, frag = ref.partition("#")
            target = page if not path else (page.parent / path)
            if path.endswith("/") or (target.exists() and target.is_dir()):
                target = target / "index.html"
            if not target.exists():
                problems.append(f"{page.relative_to(ROOT).as_posix()}: {ref}")
                continue
            if frag and target.suffix == ".html" and frag not in parse_page(target).ids:
                problems.append(f"{page.relative_to(ROOT).as_posix()}: #{frag} not found in {target.name}")
    md_link = re.compile(r"\]\(([^)\s]+)\)")
    docs = [ROOT / "README.md", ROOT / "SECURITY.md"] + sorted((ROOT / "research").glob("*/README.md")) \
        + sorted(BENCHMARK.rglob("*.md"))
    for doc in docs:
        if not doc.exists():
            continue
        for ref in md_link.findall(doc.read_text(encoding="utf-8")):
            if re.match(r"^[a-z]+:", ref) or ref.startswith("#"):
                continue
            count += 1
            target = (doc.parent / ref.split("#")[0])
            if not target.exists():
                problems.append(f"{doc.relative_to(ROOT).as_posix()}: {ref}")
    return Result("repo.internal_links", FAIL if problems else PASS,
                  "; ".join(problems) if problems else f"{count} relative links resolve (site pages and repository docs)")


def check_secrets() -> Result:
    findings = secretscan.scan()
    return Result("repo.secret_scan", FAIL if findings else PASS,
                  "; ".join(findings[:20]) if findings else
                  f"{len(secretscan.candidate_files())} publishable files scanned; no credentials, private paths, "
                  "internal hosts, IP addresses, e-mail addresses or phone numbers")


def check_reproducible(note: Note) -> Result:
    from .pdf import render_pdf
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / note.pdf_path.name
        render_pdf(note, out)
        rebuilt = sha256_file(out)
    committed = parse_sums(note.sums_path)[note.pdf_path.name]
    return Result(f"note{note.number}.pdf_reproducible", PASS if rebuilt == committed else FAIL,
                  f"rebuilt PDF sha256 {rebuilt[:16]}… {'==' if rebuilt == committed else '!='} "
                  f"SHA256SUMS {committed[:16]}…")
