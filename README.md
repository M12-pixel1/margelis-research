# Margelis Research

Technical research notes and draft benchmark specifications published by
Rūpestėlis Holding.

| Note | Title | Version | Date | Status |
| --- | --- | --- | --- | --- |
| [001](research/001/) | From Mandate to Verified Outcome: An Evaluation Framework for Autonomous Agent Execution | 1.0 | 2026-09-16 | Concept + Evaluation Framework |

## Research Note 001

- Markdown (canonical source): [`research/001/Margelis_Research_Note_001.md`](research/001/Margelis_Research_Note_001.md)
- PDF: [`research/001/Margelis_Research_Note_001.pdf`](research/001/Margelis_Research_Note_001.pdf)
- Release manifest and digests: [`metadata.json`](research/001/metadata.json), [`SHA256SUMS`](research/001/SHA256SUMS)
- GitHub release: [`research-note-001-v1.0`](https://github.com/M12-pixel1/margelis-research/releases/tag/research-note-001-v1.0)
- Canonical web page: <https://rupestelisholding.com/research/001/>; mirror built from this repository: <https://m12-pixel1.github.io/margelis-research/research/001/>
- Where it is published, DOI and verification results: [`publication-receipt.json`](research/001/publication-receipt.json)
- How to cite: [`CITATION.cff`](CITATION.cff) (GitHub shows it under "Cite this repository")

The note is positioned as an integrated evaluation framework and benchmark
boundary. It does not claim that authority continuity, delegation, runtime
authorization, receipts or verified outcomes are new; section 7 of the note
lists prior art.

## Benchmark

[`benchmark/v0.2/`](benchmark/v0.2/) holds the **draft** specification of the
Verified Delegation Benchmark: ten machine-readable scenarios, a scenario schema
and a draft receipt schema. No implementation and no results are published.

## Repository layout

```text
research/<NNN>/        note.yaml (input), <note>.md (source), <note>.pdf, metadata.json,
                       SHA256SUMS, references.json, publication-receipt.json
benchmark/v0.2/        SPEC.md, scenarios/, schemas/, results/ (empty)
site/                  generated static pages (deployed to the mirror and the canonical host)
tools/                 publication pipeline, schemas, bundled fonts
.github/workflows/     validate (every push), pages (mirror), publish-note (manual)
```

## Verify a published note

```bash
sha256sum -c SHA256SUMS                                  # next to the downloaded files
gh release verify research-note-001-v1.0 -R M12-pixel1/margelis-research
pip install -r tools/requirements.txt
python tools/publish.py verify 001 --rebuild --online    # all checks + byte-for-byte PDF rebuild
```

## Publish a new note

```bash
python tools/publish.py new 002 --title "..." --subtitle "..."
# edit research/002/note.yaml, the Markdown file and references.json
./publish-research-note 002          # build + checks; stops before publication
git add -A && git commit -m "Research Note 002 v1.0" && git push
python tools/publish.py release 002  # immutable GitHub release, assets verified after upload
python tools/publish.py zenodo 002   # private Zenodo draft + reserved DOI (needs ZENODO_ACCESS_TOKEN)
python tools/publish.py zenodo 002 --publish --confirm-doi <DOI>   # irreversible; needs a granted license
python tools/publish.py build 002 && python tools/publish.py receipt 002
```

Rules the pipeline enforces:

- A released version is never overwritten. Corrections become `v1.1`, conceptual changes `v2.0`.
- The PDF is byte-reproducible from the Markdown source, the pinned tool versions and the bundled fonts.
- `metadata.json` is immutable per version; a DOI assigned later is recorded in
  `publication-receipt.json`, `CITATION.cff`, the web page and the release notes.
- No license is written anywhere until it is granted in `note.yaml`; without it
  the Zenodo step keeps the draft closed and refuses to publish.
- Every publishable file is scanned for credentials and private operational data.

## Not in this repository

Production code, enforcement logic, credentials, customer data, internal
datasets, private benchmarks and confidential architectures.

## License

Pending. See [`LICENSE`](LICENSE).
