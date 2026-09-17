"""Offline test of the Zenodo flow against a simulated API (no network, no token)."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mrpub import zenodo  # noqa: E402
from mrpub.common import Note, PipelineError, load_note, md5_file  # noqa: E402

BASE = zenodo.API["production"]


class FakeClient:
    """Mimics the legacy deposit API closely enough to exercise every branch of zenodo.run()."""

    def __init__(self, fail_update=False, license_as_dict=True):
        self.deps, self.fail_update, self.license_as_dict = {}, fail_update, license_as_dict
        self.deleted, self.next_id = [], 101

    def _new(self, files=()):
        dep_id = self.next_id
        self.next_id += 1
        dep = {"id": dep_id, "record_id": dep_id, "conceptrecid": "100", "submitted": False,
               "files": [dict(f) for f in files], "metadata": {},
               "links": {"bucket": f"bucket://{dep_id}", "html": f"https://example.test/deposit/{dep_id}",
                         "latest_draft": f"{BASE}/deposit/depositions/{dep_id}"}}
        self.deps[dep_id] = dep
        return dep

    def create(self):
        return self._new()

    def get(self, dep_id):
        return self.deps[dep_id]

    def get_url(self, url):
        return self.deps[int(url.rsplit("/", 1)[1])]

    def update(self, dep_id, metadata):
        if self.fail_update:
            raise PipelineError("simulated 400 on metadata")
        md = dict(metadata)
        md.pop("prereserve_doi")
        if "license" in md and self.license_as_dict:
            md["license"] = {"id": md["license"]}
        md["prereserve_doi"] = {"doi": f"10.5281/zenodo.{dep_id}", "recid": dep_id}
        self.deps[dep_id]["metadata"] = md
        return self.deps[dep_id]

    def upload(self, bucket, path):
        dep_id = int(bucket.split("://")[1])
        entry = {"id": f"f-{path.name}", "filename": path.name, "checksum": md5_file(path)}
        self.deps[dep_id]["files"].append(entry)
        return {"checksum": f"md5:{entry['checksum']}"}

    def delete_file(self, dep_id, file_id):
        self.deleted.append(file_id)
        self.deps[dep_id]["files"] = [f for f in self.deps[dep_id]["files"] if f["id"] != file_id]

    def newversion(self, dep_id):
        # the API returns the ORIGINAL deposition; the draft carries a snapshot of the old files
        draft = self._new(files=[{"id": "old-1", "filename": "old-note.pdf", "checksum": "0" * 32}])
        original = dict(self.deps.setdefault(dep_id, {"id": dep_id, "links": {}}))
        original["links"] = {"latest_draft": draft["links"]["latest_draft"]}
        return original

    def publish(self, dep_id):
        self.deps[dep_id].update(submitted=True, doi=f"10.5281/zenodo.{dep_id}", conceptdoi="10.5281/zenodo.100")
        return {}


def run_case(label, client, *, expect_exit=None, expect_error=None, seed=None, check=None, **kw):
    note = load_note("001")
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "zenodo.json"
        if seed is not None:
            target.write_text(json.dumps(seed), encoding="utf-8")
        original = Note.zenodo_path
        Note.zenodo_path = property(lambda self: target)
        zenodo.Client = lambda env: client
        try:
            try:
                code = zenodo.run(note, **kw)
                ok = expect_error is None and code == expect_exit
                detail = f"exit={code}"
            except PipelineError as exc:
                ok = expect_error is not None and expect_error in str(exc)
                detail = f"error={str(exc)[:70]}"
            recorded = target.exists()
            extra = check(note, client) if (check and ok) else ""
            if extra:
                ok, detail = False, f"{detail}; {extra}"
        finally:
            Note.zenodo_path = original
    ok = ok and recorded
    print(f"{'PASS' if ok else 'FAIL'} {label}: {detail}; zenodo.json written={recorded}")
    return ok


def check_new_version(note, client):
    records = note.zenodo_records()
    problems = []
    if "old-1" not in client.deleted:
        problems.append("inherited file was not deleted")
    current = records.get(note.version, {})
    if current.get("previous_version") != "0.9":
        problems.append(f"previous_version={current.get('previous_version')!r}")
    if "0.9" not in records:
        problems.append("earlier version record was lost")
    names = {f["filename"] for f in client.deps[current.get("deposition_id")]["files"]}
    if names != {f.name for f in zenodo.upload_files(note)}:
        problems.append(f"draft files {sorted(names)}")
    return "; ".join(problems)


def main() -> int:
    note = load_note("001")
    granted = note.license_granted
    earlier = {"records": {"0.9": {"environment": "production", "version": "0.9", "deposition_id": 50,
                                   "state": "published", "doi": "10.5281/zenodo.50",
                                   "concept_doi": "10.5281/zenodo.100"}}}
    results = [
        run_case("draft with license returned as object", FakeClient(), expect_exit=0),
        run_case("failed metadata update still records the draft", FakeClient(fail_update=True),
                 expect_error="simulated 400"),
        run_case("new version of a published earlier version", FakeClient(), expect_exit=0, seed=earlier,
                 check=check_new_version),
    ]
    if granted:
        results += [
            run_case("publish refused without matching DOI", FakeClient(),
                     expect_error="does not match the reserved DOI", publish=True, confirm_doi="10.5281/zenodo.999"),
            run_case("publish with the reserved DOI", FakeClient(), expect_exit=0,
                     publish=True, confirm_doi="10.5281/zenodo.101"),
        ]
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
