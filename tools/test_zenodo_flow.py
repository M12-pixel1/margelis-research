"""Offline test of the Zenodo flow against a simulated API (no network, no token)."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mrpub import zenodo  # noqa: E402
from mrpub.common import PipelineError, load_note, md5_file  # noqa: E402


class FakeClient:
    def __init__(self, env, fail_update=False, license_as_dict=True):
        self.deps, self.fail_update, self.license_as_dict = {}, fail_update, license_as_dict

    def create(self):
        dep = {"id": 101, "record_id": 101, "conceptrecid": "100", "submitted": False, "files": [],
               "metadata": {}, "links": {"bucket": "bucket://101", "html": "https://example.test/deposit/101"}}
        self.deps[101] = dep
        return dep

    def get(self, dep_id):
        return self.deps[dep_id]

    def update(self, dep_id, metadata):
        if self.fail_update:
            raise PipelineError("simulated 400 on metadata")
        md = dict(metadata)
        md.pop("prereserve_doi")
        if "license" in md and self.license_as_dict:
            md["license"] = {"id": md["license"]}
        md["prereserve_doi"] = {"doi": "10.5281/zenodo.101", "recid": 101}
        self.deps[dep_id]["metadata"] = md
        return self.deps[dep_id]

    def upload(self, bucket, path):
        entry = {"filename": path.name, "checksum": md5_file(path)}
        self.deps[101]["files"].append(entry)
        return {"checksum": f"md5:{entry['checksum']}"}

    def publish(self, dep_id):
        self.deps[dep_id].update(submitted=True, doi="10.5281/zenodo.101")
        return {}


def run_case(label, client, expect_exit=None, expect_error=None, **kw):
    note = load_note("001")
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "zenodo.json"
        orig = type(note).zenodo_path
        type(note).zenodo_path = property(lambda self: target)
        zenodo.Client = lambda env: client
        try:
            code = zenodo.run(note, **kw)
            ok = expect_error is None and code == expect_exit
            detail = f"exit={code}"
        except PipelineError as exc:
            ok = expect_error is not None and expect_error in str(exc)
            detail = f"error={str(exc)[:70]}"
        finally:
            type(note).zenodo_path = orig
        recorded = target.exists()
    ok = ok and recorded
    print(f"{'PASS' if ok else 'FAIL'} {label}: {detail}; zenodo.json written={recorded}")
    return ok


note = load_note("001")
results = [
    run_case("draft with license returned as object", FakeClient("production"), expect_exit=0),
    run_case("failed metadata update still records the draft", FakeClient("production", fail_update=True),
             expect_error="simulated 400"),
    run_case("publish refused without matching DOI", FakeClient("production"),
             expect_error="does not match the reserved DOI", publish=True, confirm_doi="10.5281/zenodo.999")
    if note.license_granted else True,
    run_case("publish with the reserved DOI", FakeClient("production"), expect_exit=0,
             publish=True, confirm_doi="10.5281/zenodo.101")
    if note.license_granted else True,
]
sys.exit(0 if all(results) else 1)
