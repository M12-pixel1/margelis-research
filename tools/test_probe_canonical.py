#!/usr/bin/env python3
"""Deterministic branch tests for receipt.probe_canonical().

No network calls are made. The test patches the receipt HTTP helpers and pins the
three public statuses plus missing-license-row behavior.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mrpub import receipt  # noqa: E402
from mrpub.common import license_display_html, load_note  # noqa: E402


class FakeResponse:
    def __init__(self, status_code: int, text: str):
        self.status_code = status_code
        self.text = text


def main() -> int:
    note = load_note("001")
    pending = {
        "status": "pending",
        "spdx": None,
        "authorized_by": None,
        "authorized_on": None,
    }

    granted_html = f"<dl><dt>License</dt><dd>{license_display_html(note.license)}</dd></dl>"
    pending_html = f"<dl><dt>License</dt><dd>{license_display_html(pending)}</dd></dl>"

    original_http_get = receipt._http_get
    original_http_probe = receipt.http_probe

    def run_case(page_status: int, body: str, pdf_matches: bool) -> dict:
        def fake_http_get(url: str):
            response = FakeResponse(page_status, body)
            return ({"url": url, "checked_at": "test", "http_status": page_status}, response)

        def fake_http_probe(url: str, expect_sha256: str | None = None):
            return {
                "url": url,
                "checked_at": "test",
                "http_status": 200 if pdf_matches else 503,
                "sha256_matches": pdf_matches,
            }

        receipt._http_get = fake_http_get
        receipt.http_probe = fake_http_probe
        return receipt.probe_canonical(note, "deadbeef")

    try:
        live = run_case(200, granted_html, True)
        assert live["status"] == "LIVE", live
        assert live["license_check"]["matches"] is True, live

        stale = run_case(200, pending_html, True)
        assert stale["status"] == "STALE_OR_INCONSISTENT", stale
        assert stale["license_check"]["matches"] is False, stale

        missing = run_case(200, "<html><body>No License row</body></html>", True)
        assert missing["status"] == "STALE_OR_INCONSISTENT", missing
        assert missing["license_check"]["observed"] is None, missing

        page_down = run_case(503, granted_html, True)
        assert page_down["status"] == "NOT_DEPLOYED", page_down

        pdf_bad = run_case(200, granted_html, False)
        assert pdf_bad["status"] == "NOT_DEPLOYED", pdf_bad
    finally:
        receipt._http_get = original_http_get
        receipt.http_probe = original_http_probe

    print("PASS probe_canonical: LIVE, STALE_OR_INCONSISTENT, NOT_DEPLOYED and missing-row paths")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
