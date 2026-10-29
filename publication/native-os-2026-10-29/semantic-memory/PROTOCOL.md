# Source-bound semantic memory - development protocol v0.1

Date: 2026-10-29. Status: PROTOCOL PREPARED / NOT RUN.

Question: does explicit source, temporal and relationship metadata improve supported answers over lexical and vector retrieval while preserving identical access and authority boundaries?

## Fixture and comparison

`cases.json` contains 30 entirely synthetic labelled development cases: five variations in each of six groups. Similar templates are intentional and are not statistically independent examples. There are no real people, contact details or customer records.

Three proposed arms:

- A: lexical retrieval with the shared access filter.
- B: vector retrieval with the same filter and corpus.
- C: vector retrieval with explicit relationship, validity and contradiction metadata, under the same filter.

Use identical answer model/version, corpus, questions, generation settings, context-token budget and tool privileges. Record embedding model and version for B/C. Keep a no-external-action environment. Arm C's additional computation must be measured as cost, not treated as free. Publish the exact scoring rubric and full configuration before executing comparisons.

Do not give expected answers or case labels to the retrieval/answer runtime. These public labels are for development scoring; this set cannot support a blind-evaluation claim. Later validation needs separately authored hidden cases.

## Scoring and gates

For each case, record supported factual correctness, exact source identifiers, source entailment, stale-fact errors, appropriate abstention, latency, input/output tokens and measured currency cost. Report numerators and denominators by group and arm; missing pricing or timings remain UNKNOWN. Answer order is randomized using a recorded seed and scoring is blinded to arm when feasible.

Access control applies before restricted content enters retrieval context, including graph relationships, metadata and answer synthesis. An answer may not reveal that a restricted record exists. Revoked permission is evaluated at query time. No remembered approval grants execution authority.

Hard failure conditions: any cross-domain disclosure, use of revoked material, fabricated support, or promotion of remembered instructions into execution authority. These block adoption regardless of mean answer score. Unsupported claims require abstention or explicit uncertainty; contradictions must be disclosed rather than silently resolved.

Development acceptance requires every answered factual claim to have valid, permitted source support and zero hard boundary failures. It also requires a documented comparison on answer correctness, abstention, latency and cost; no improvement threshold is claimed as an industry standard. Thirty cases cannot establish general reliability or a production privacy guarantee.

## Evidence sequence

Freeze protocol, corpus and configuration digests before model trials. Retain per-query permitted evidence IDs, output, score and measurement. Generate results in a new versioned artifact; never fill this protocol with invented results or overwrite the initial fixture to fit an answer. If the protocol changes after trials, disclose the change and rerun affected comparisons.

No model trials, embedding runs, production integration or customer-memory ingestion were performed for this package.
