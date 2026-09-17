"""Shared paths, loaders and small helpers for the publication pipeline."""
from __future__ import annotations

import datetime as dt
import hashlib
import html as html_lib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
FONTS = TOOLS / "fonts"
SCHEMAS = TOOLS / "schemas"
SITE = ROOT / "site"
RESEARCH = ROOT / "research"
BENCHMARK = ROOT / "benchmark"

MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]


class PipelineError(RuntimeError):
    """A condition that must stop the pipeline."""


def load_yaml(path: Path):
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_json(path: Path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def write_text(path: Path, text: str) -> None:
    """Write UTF-8 with LF line endings on every platform."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def write_json(path: Path, obj) -> None:
    write_text(path, json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def md5_file(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def human_date(iso: str) -> str:
    d = dt.date.fromisoformat(iso)
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def epoch_of(iso: str) -> int:
    d = dt.date.fromisoformat(iso)
    return int(dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc).timestamp())


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def slugify(text: str) -> str:
    """GitHub-compatible heading anchor."""
    s = text.strip().lower()
    s = re.sub(r"[^\w\- ]", "", s, flags=re.UNICODE)
    return s.replace(" ", "-")


def strip_number(heading: str) -> str:
    """'9. What remains unproven' -> 'What remains unproven'."""
    return re.sub(r"^\d+(\.\d+)*\.?\s+", "", heading.strip())



LICENSE_PENDING_TEXT = "Not yet granted: a license decision is pending, so no reuse rights are granted at this time."
LICENSE_SCOPE_TEXT = "(applies to the note text only)"


def license_is_granted(license_meta: dict) -> bool:
    return license_meta.get("status") == "granted" and bool(license_meta.get("spdx")) \
        and bool(license_meta.get("authorized_by")) and bool(license_meta.get("authorized_on"))


def license_display_text(license_meta: dict) -> str:
    """Canonical human-visible license wording used by both rendering and verification."""
    if license_is_granted(license_meta):
        return f"{license_meta['spdx']} {LICENSE_SCOPE_TEXT}"
    return LICENSE_PENDING_TEXT


def license_display_html(license_meta: dict) -> str:
    """Canonical HTML for the human-visible License row."""
    if not license_is_granted(license_meta):
        return html_lib.escape(LICENSE_PENDING_TEXT)
    spdx = str(license_meta["spdx"])
    href = f"https://spdx.org/licenses/{html_lib.escape(spdx, quote=True)}.html"
    return f'<a href="{href}">{html_lib.escape(spdx)}</a> {html_lib.escape(LICENSE_SCOPE_TEXT)}'


def extract_license_text(body: str) -> str | None:
    """Extract and normalize the human-visible License row from a generated note page."""
    match = re.search(r"<dt>\s*License\s*</dt>\s*<dd>(.*?)</dd>", body, flags=re.I | re.S)
    if not match:
        return None
    plain = re.sub(r"<[^>]+>", " ", match.group(1))
    return " ".join(html_lib.unescape(plain).split())


def canonical_license_check(body: str, license_meta: dict) -> dict:
    expected = license_display_text(license_meta)
    observed = extract_license_text(body)
    return {"expected": expected, "observed": observed, "matches": observed == expected}


def git(*args: str, check: bool = True) -> str:
    out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    if check and out.returncode != 0:
        raise PipelineError(f"git {' '.join(args)} failed: {out.stderr.strip()}")
    return out.stdout.strip()


def load_series() -> dict:
    return load_yaml(ROOT / "series.yaml")


def parse_sums(path: Path) -> dict[str, str]:
    sums = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, name = line.split(maxsplit=1)
        sums[name.lstrip("*").strip()] = digest
    return sums


@dataclass
class Note:
    number: str
    meta: dict
    series: dict

    # --- locations -------------------------------------------------------
    @property
    def dir(self) -> Path:
        return RESEARCH / self.number

    @property
    def stem(self) -> str:
        return f"Margelis_Research_Note_{self.number}"

    @property
    def md_path(self) -> Path:
        return self.dir / f"{self.stem}.md"

    @property
    def pdf_path(self) -> Path:
        return self.dir / f"{self.stem}.pdf"

    @property
    def metadata_path(self) -> Path:
        return self.dir / "metadata.json"

    @property
    def sums_path(self) -> Path:
        return self.dir / "SHA256SUMS"

    @property
    def receipt_path(self) -> Path:
        return self.dir / "publication-receipt.json"

    @property
    def zenodo_path(self) -> Path:
        return self.dir / "zenodo.json"

    @property
    def references_path(self) -> Path:
        return self.dir / "references.json"

    @property
    def site_dir(self) -> Path:
        return SITE / "research" / self.number

    @property
    def site_version_dir(self) -> Path:
        return self.site_dir / f"v{self.version}"

    # --- identity --------------------------------------------------------
    @property
    def version(self) -> str:
        return str(self.meta["version"])

    @property
    def date(self) -> str:
        return str(self.meta["date"])

    @property
    def tag(self) -> str:
        return f"research-note-{self.number}-v{self.version}"

    @property
    def title(self) -> str:
        return self.meta["title"]

    @property
    def subtitle(self) -> str:
        return self.meta["subtitle"]

    @property
    def full_title(self) -> str:
        return f"{self.title}: {self.subtitle}"

    @property
    def authors(self) -> list[dict]:
        return self.meta["authors"]

    @property
    def author_names(self) -> list[str]:
        return [f"{a['given_name']} {a['family_name']}" for a in self.authors]

    @property
    def series_name(self) -> str:
        return self.series["series"]

    @property
    def publisher(self) -> str:
        return self.series["publisher"]

    @property
    def repo_url(self) -> str:
        return self.series["repository"]["url"]

    @property
    def repo_slug(self) -> str:
        r = self.series["repository"]
        return f"{r['owner']}/{r['name']}"

    @property
    def canonical_url(self) -> str:
        return f"{self.series['site']['canonical_base']}{self.number}/"

    @property
    def preview_url(self) -> str:
        return f"{self.series['site']['preview_base']}{self.number}/"

    @property
    def pdf_url(self) -> str:
        return f"{self.canonical_url}v{self.version}/{self.pdf_path.name}"

    @property
    def release_url(self) -> str:
        return f"{self.repo_url}/releases/tag/{self.tag}"

    @property
    def og_image_name(self) -> str:
        return f"og-{self.number}-v{self.version}.png"

    @property
    def label(self) -> str:
        return f"Research Note {self.number} · v{self.version} · {human_date(self.date)}"

    @property
    def license(self) -> dict:
        return self.meta["license"]

    @property
    def license_granted(self) -> bool:
        return license_is_granted(self.license)

    def zenodo_records(self) -> dict[str, dict]:
        """version -> Zenodo record. Accepts the single-record layout written before versioning."""
        if not self.zenodo_path.exists():
            return {}
        data = load_json(self.zenodo_path)
        if "records" in data:
            return data["records"]
        return {str(data["version"]): data} if data.get("version") else {}

    def zenodo_record(self, version: str | None = None) -> dict | None:
        return self.zenodo_records().get(version or self.version)

    def version_doi(self, version: str) -> str | None:
        """DOI of a version, only once its Zenodo record is published."""
        rec = self.zenodo_record(version)
        if rec and rec.get("state") == "published" and rec.get("doi"):
            return rec["doi"]
        return None

    def doi(self) -> str | None:
        return self.version_doi(self.version)

    def concept_doi(self) -> str | None:
        """DOI that always resolves to the latest published version."""
        for rec in self.zenodo_records().values():
            if rec.get("state") == "published" and rec.get("concept_doi"):
                return rec["concept_doi"]
        return None

    def previous_versions(self) -> list[str]:
        return [str(h["version"]) for h in self.meta["version_history"] if str(h["version"]) != self.version]


def load_note(number: str) -> Note:
    number = f"{int(number):03d}"
    path = RESEARCH / number / "note.yaml"
    if not path.exists():
        raise PipelineError(f"{path} not found (use `publish.py new {number}` to scaffold)")
    meta = load_yaml(path)
    if str(meta.get("number")) != number:
        raise PipelineError(f"{path}: number field {meta.get('number')!r} != directory {number!r}")
    return Note(number=number, meta=meta, series=load_series())


def all_notes() -> list[str]:
    return sorted(p.name for p in RESEARCH.iterdir() if p.is_dir() and (p / "note.yaml").exists())
