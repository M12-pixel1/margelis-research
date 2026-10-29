"""Render the working-paper preview using the existing research PDF renderer.

Run from the repository root after installing tools/requirements.txt.
This does not register, release, license or publish a numbered research note.
"""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))

from mrpub.common import Note, load_series  # noqa: E402
from mrpub import pdf as pdf_renderer  # noqa: E402


class PreviewRenderer(pdf_renderer.Renderer):
    def table(self, node):
        table = super().table(node)
        table._keep = True
        return table


class WorkingPaper(Note):
    @property
    def md_path(self):
        return PACKAGE / "Native_OS_Working_Paper_EN.md"

    @property
    def label(self):
        return "Working Paper v0.1 - 29 October 2026"


def main():
    meta = {
        "version": "0.1", "date": "2026-10-29",
        "title": "MARGELIS Native OS",
        "subtitle": "An Evidence-Bound Control Plane for Agent Execution",
        "authors": [{"given_name": "Tomas", "family_name": "Margelis",
                     "affiliation": "Rūpestėlis Holding - AI-assisted draft for author review"}],
        "status": "Architecture working draft; reference self-tests only; author review pending",
        "keywords": ["AI agents", "delegated authority", "verified outcomes", "enterprise control plane"],
        "language": "en",
    }
    note = WorkingPaper(number="WIP", meta=meta, series=load_series())
    output = PACKAGE / "Native_OS_Working_Paper_EN.pdf"
    # Keep this paper's short tables together without changing the shared renderer.
    pdf_renderer.Renderer = PreviewRenderer
    info = pdf_renderer.render_pdf(note, output)
    print(json.dumps({"file": output.name, **info}))


if __name__ == "__main__":
    main()
