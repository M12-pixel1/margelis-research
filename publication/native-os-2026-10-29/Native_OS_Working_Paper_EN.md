MARGELIS RESEARCH

# MARGELIS Native OS

**An Evidence-Bound Control Plane for Agent Execution**

Tomas Margelis - proposed author, review pending\
Rūpestėlis Holding\
Working Paper v0.1 - 29 October 2026

---

**Status: architecture working draft with a reproduced reference self-test.** This document reports three synthetic scenario types, each repeated twice at each of two reference-test stages. It does not evaluate the deployed Native OS, third-party agents or customer outcomes. AI assisted preparation; the author has not yet approved this exact version.

## 1. The problem and the proposed contribution

An agent can receive an instruction, call a tool and report success without establishing that the action was authorized at execution time or that the requested external outcome occurred. Longer-running tasks add stale approvals, retries, changed context and substituted executors to this gap.

MARGELIS Native OS is an enterprise operating-layer architecture for connecting human decisions to bounded agent execution and checkable outcomes. Here, OS names the coordination layer above existing applications and host operating systems. It does not describe a replacement Linux kernel or a general-purpose desktop operating system.

The proposed contribution is a concrete separation of proposal, approval, execution authority, worker routing and outcome verification, together with explicit evidence requirements at their boundaries. The underlying concepts have prior art. Architectural integration and domain-specific usefulness remain hypotheses to evaluate, rather than claims of priority or demonstrated competitive advantage. The earlier Margelis evaluation framework establishes the mandate-to-outcome question [1].

## 2. Architecture and authority boundaries

The control plane coordinates separately deployable workers. Existing business systems remain the authoritative records for their respective domains. A reasoning model may prepare an action, retrieve relevant information and explain a result; authority and verified completion require evidence outside that explanation.

| Boundary | Required object or observation | What it must not imply |
| --- | --- | --- |
| Human intent to proposal | A bounded task and its source | Natural-language intent alone is not authenticated authority |
| Approval to decision | Authenticated approval bound to the exact decision | Approval does not by itself grant every required execution permission |
| Decision to authorized action | Current mandate, scope and policy checks | An old approval cannot silently survive a material change |
| Authorized action to worker | Explicit capability, identity and action binding | Routing a task does not mean it executed |
| Worker to outcome | Authoritative state readback with provenance | A successful tool response or the worker's own DONE is insufficient |
| Outcome to receipt | Bound evidence, result and known limitations | A signed receipt does not make an unreliable observation true |

The intended flow is: authenticated human decision, bounded task, execution-time authorization, selected domain worker, external state observation, outcome binding, and a recorded state transition. No worker may expand its mandate by writing a memory entry or by passing instructions to another worker.

Documents, web pages, emails and retrieved memories are input data. Instructions embedded within them may support a proposal but cannot become their own mandate. Authorization needs to be checked again immediately before the material effect. If the external effect becomes uncertain, the system must preserve that uncertainty and reconcile state before retrying a potentially non-idempotent action.

The architecture permits a shared control contract without merging all workers into one runtime. This separation supports bounded access and independent rollback. It is an architectural objective; comprehensive enforcement across real adapters is outside the evidence reported here.

## 3. Memory, meaning and original evidence

Semantic access can reduce the need to remember folder names. It does not remove the need for original records, stable identifiers, access control or version history. Vector retrieval ranks similarity; a knowledge graph can explicitly represent entities, relationships and temporal qualifications. Neither representation, on its own, establishes truth or authority.

A proposed memory entry should retain its source identifier, source version or digest, observation time, validity interval when known, permitted audience and claim type. Observed facts, inferences, forecasts and unknowns should remain distinguishable. Contradictory sources should remain visible until resolved under a documented rule.

Personal cognitive memory, institutional memory and family heritage archives require separate access boundaries. A controlled bridge may disclose the minimum authorized material for a purpose. It should not join all three into one unrestricted pool. In a heritage example, a generated summary of a relative's story should remain distinguishable from the original account and point back to the permitted original. In an enterprise example, a remembered price decision should identify its scope and period of validity.

These are design requirements. No retrieval-quality improvement, cross-domain privacy guarantee or semantic-memory runtime result is claimed by this paper.

## 4. Related work and the meaning of agent-native

Agent-native is used for different layers of the computing stack. Comparing projects requires identifying both their layer and the evidence supporting their claims.

| Work | Layer and public evidence | Relationship to this proposal |
| --- | --- | --- |
| AIOS [2] | Research architecture and code for agent scheduling, context, memory, storage and access control; COLM 2025 paper | Agent execution resources complement an enterprise authority-and-outcome contract |
| YoloFS [3] | SOSP 2026 filesystem research with staged changes, snapshots and access gating | Filesystem enforcement can constrain a worker beneath the enterprise control plane |
| AE-OS [4] | Early-stage enterprise architecture and toolkit with agent identity, delegated authority and receipts | Closely related enterprise problem; no comparative performance result is asserted here |
| Noesis OS [5] | Developer describes a kernel-level OS with governed execution and semantic memory; private beta scheduled for January 2027 | Potential infrastructure direction; vendor declarations are not independently reproduced results |

These sources do not establish the end of filesystems. YoloFS explicitly retains the filesystem and strengthens its role in agent control. Nor does a public architecture page establish that its deployment, security or economic claims have been independently verified. The same evidence standard applies to MARGELIS.

## 5. Reproducible reference demonstration

We reran the existing public Verified Delegation Benchmark P0 reference code [6] from source commit d6f532dfcfa28df7828dfec6db63a0f752d3567b. No benchmark logic was changed. The evidence directory records source-file digests, dependency versions, the execution date and the four raw result bundles.

The harness compares deliberately unsafe and guarded reference behaviours for three predefined cases. A second stage places synthetic authoritative state in a separate HTTP/SQLite process and uses readback. The sandbox still belongs to the same experimental trust domain. Both stages were executed twice in the task workspace.

| Scenario | Unsafe reference, both repeats at both stages | Guarded reference, both repeats at both stages |
| --- | --- | --- |
| Expired mandate | Fails: a synthetic material effect occurs after authority expiry | Passes: no new effect, reauthorization required |
| Replay | Fails: two synthetic payments remain for the repeated delivery | Passes: the original single payment remains and the replay is denied |
| False DONE | Fails: completion is reported despite unchanged authoritative fixture state | Passes: readback mismatch produces a failed outcome |

Thus each guarded system passed three of three checks in each of its two runs. Each unsafe system failed three of three, as expected for the negative control. Repeats are not additional scenario coverage and must not be presented as independent statistical observations.

This exercise confirms that the existing reference demonstration is reproducible in this workspace and distinguishes its intentionally different behaviours. The deterministic harness is substantially fixture-defined; even the process sandbox is a synthetic reference implementation. It does not establish that an actual Native OS adapter resists these failures, or that arbitrary agents preserve the same invariants. No production system, live payment, telephone call or customer record was used. The reproduction was AI assisted, not an independent institutional replication.

## 6. Proposed next experiment: source-bound semantic memory

An accompanying protocol and 30 synthetic development cases specify a separate experiment. They contain no measured retrieval results. The six groups cover temporal updates, contradictions, revoked access, personal/enterprise separation, source traceability and insufficient evidence.

The proposed comparison uses a lexical baseline, a vector-retrieval baseline, and retrieval augmented by explicit relationships and validity metadata. All arms must use the same corpus, questions, access policies, answer model, context budget and scoring rules. Denied material must be filtered before it reaches the answer model; post-generation suppression alone is insufficient.

Primary measures are supported-answer accuracy and source support. Access-boundary violations and promotion of memory into authority are hard failure conditions. Secondary measures include stale-fact errors, appropriate abstention, latency and measured cost. Changing the retrieval method must not change execution permissions.

These public, templated, labelled cases are development fixtures, not a blind evaluation or a representative population sample. A later hidden holdout and independently checked scoring are necessary before making generalization claims. The present status is PROTOCOL PREPARED / NOT RUN.

## 7. Operational and commercial interpretation

The intended customer benefit is a service that can explain what was requested, what it was allowed to do, what it actually did and what evidence confirms the result. For example, a service could distinguish a proposed appointment time, a submitted booking request and an independently confirmed booking.

That benefit must be measured against existing practice. Useful prospective outcomes include verified task completion, unresolved exceptions, operator minutes per verified outcome, and execution plus verification cost. They require actual service evidence and an appropriate comparison. This paper reports none of these commercial or clinical outcomes and proposes no medical effectiveness claim.

## 8. What remains unproven

- The reference runs do not validate the deployed MARGELIS Native OS or any commercial agent.
- End-to-end adapter identity, durable mandate revocation, concurrency and failure recovery are not established by the reported runs.
- Independent external verification is only as reliable as its source and binding; a signature alone does not establish external truth.
- Semantic-memory quality, privacy enforcement, latency and economic benefit have not been measured in this package.
- No comparative advantage over AIOS, YoloFS, AE-OS, Noesis OS or other products has been demonstrated.
- Three designed scenario types and deterministic repeats do not estimate real-world failure rates.
- The source reproducer and publisher are not independent evaluators.
- A working draft, DOI, repository release or passing self-test is not a certification, security audit or production-readiness decision.

## 9. References

1. Margelis, T. From Mandate to Verified Outcome: An Evaluation Framework for Autonomous Agent Execution. Margelis Research Note 001, v1.1, 17 September 2026. <https://doi.org/10.5281/zenodo.22806682>. Repository record: <https://github.com/M12-pixel1/margelis-research/tree/d6f532dfcfa28df7828dfec6db63a0f752d3567b/research/001>. Prior publication; this working draft does not amend it.
2. Mei, K. et al. AIOS: LLM Agent Operating System. arXiv:2403.16971v5; COLM 2025. <https://arxiv.org/abs/2403.16971>. Primary paper inspected 29 October 2026.
3. Zhong, S. et al. Don't Let AI Agents YOLO Your Files: Information and Control in Agent-Native Filesystems. SOSP 2026; DOI 10.1145/3830418.3843858. <https://yolofs.github.io/>. Author project and linked paper inspected 29 October 2026.
4. Lentz, D. AE-OS: The Agent-Native Enterprise Operating System. <https://ae-os.org/>. Project's own early-stage architecture and demonstration, inspected 29 October 2026; no independent product validation implied.
5. Pensiv Inc. Noesis OS. <https://runnoesis.com/>. Vendor development page, inspected 29 October 2026; beta date and capabilities are vendor statements.
6. Rūpestėlis Holding. Verified Delegation Benchmark v0.2 P0 reference harness and process sandbox. <https://github.com/M12-pixel1/margelis-research/tree/d6f532dfcfa28df7828dfec6db63a0f752d3567b/benchmark/v0.2>. Source inspected and rerun 29 October 2026. Raw outputs accompany this draft.

---

## About this document

Working Paper v0.1, 29 October 2026. AI-assisted draft for author review. No DOI has been assigned to this working paper. No reuse license has yet been assigned to this package. The license of Research Note 001 remains limited to its own stated scope. Production source, enforcement internals and customer data are outside this publication.
