# MARGELIS Native OS - public-review working draft

Version 0.1 | 29 October 2026 | Rūpestėlis Holding

This package describes an enterprise control-plane architecture and supplies a reproduction of an existing public reference demonstration. It is work in progress, open for technical criticism. It is not a production-readiness announcement or a numbered DOI release.

- [Technical working paper (English)](Native_OS_Working_Paper_EN.md)
- [Business explanation (Lithuanian)](Native_OS_Brief_LT.md)
- [Demonstration script](DEMO.md)
- [Reproduction instructions](REPRODUCE.md)
- [Source provenance and run inventory](evidence/provenance.json)
- [Semantic-memory experiment protocol](semantic-memory/PROTOCOL.md)
- [Thirty synthetic development cases](semantic-memory/cases.json)
- [Package digests](SHA256SUMS)

## What can be checked now

Three existing public scenarios - expired mandate, replay and false completion - were rerun twice in a deterministic harness and twice in a separate-process HTTP/SQLite sandbox. In each run, the guarded reference passed all three scenario checks and the deliberately unsafe reference failed all three. The unsafe failures are expected negative controls.

These are publisher-defined reference behaviours. Neither stage executes the private Native OS control plane, a commercial agent or a customer workflow. The runs demonstrate the reference test's distinction; they do not establish Native OS production safety, measured business benefit or superiority over competitors. The sandbox is a separate synthetic process, not an independent institution or real-world authority.

The semantic-memory experiment is specified but NOT RUN. Its 30 labelled cases are a public development fixture, not a blind validation set.

## Publication boundary

No production source, enforcement internals, credentials or customer data are included. Existing Research Note 001 remains unchanged. This working draft has no newly assigned DOI and is not peer reviewed. A reuse license has not been assigned to this package; the license of Research Note 001 does not automatically extend to it. AI assisted drafting, source inspection and reproduction; author review remains pending.

The intended next formal artifact is a reviewed research note with an explicit license decision and a versioned release. A DOI or release signature would identify and preserve that artifact; it would not certify its claims.
