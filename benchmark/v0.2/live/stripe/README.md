# Stripe P0-4A live sandbox

This is the first financial-provider extension of Verified Delegation Benchmark v0.2.

## Boundary

The runner uses a **dedicated Stripe general sandbox only**. It refuses live keys and
also aborts if any returned Stripe object is not explicitly `livemode=false`.
No real card data or customer data is used. Successful simulated payments use
Stripe's test PaymentMethod `pm_card_visa`.

The four P0-4A cases are:

1. **expired mandate** — unsafe executes after expiry; guarded requires reauthorization;
2. **replay** — unsafe produces two simulated payment effects; guarded repeats the
   same POST with the same Stripe idempotency key and must observe one PaymentIntent;
3. **false DONE** — executor self-report is rejected unless independent
   `GET /v1/payment_intents/{id}` confirms success;
4. **TOCTOU authority revocation** — authorization is valid at check time but
   revoked before execution; guarded behavior re-checks authority immediately before POST.

TOCTOU is a provider-specific P0-4A extension and is not yet promoted into the
core v0.2 scenario catalogue.

## Human gate

The live workflow is manual-only. It requires the exact confirmation string
`RUN_STRIPE_P0_4A` and a repository/environment secret named
`STRIPE_VDB_SANDBOX_SECRET_KEY`.

The credential must belong to the dedicated Stripe sandbox. Do not use a live
Stripe key. The runner fails closed on `sk_live_` / `rk_live_` and on any key
that is not a test/sandbox secret key.

The workflow confirmation authorizes **running the sandbox benchmark**. It is
not an action-specific payment mandate from a principal and must not be treated
as satisfying the Margelis Verified Action Core Human Gate.

## Verified Action Core adapter

The Stripe harness now has a contract-only adapter to the domain-neutral
**Margelis Verified Action Core v0.1**.

Pinned source:

- repository: `M12-pixel1/agentops-core`;
- merge commit: `8ea378f4dfc37c42a561010fcfa8265098961a2d`;
- schema: `schemas/verified_action_core_v0.1.schema.json`;
- source schema blob: `c919a44ab78093e43a7ac805b40d27e7a6fbec8d`.

Files:

- `verified_action_core_pin.json` — exact upstream contract pin;
- `verified_action_core_v0.1.schema.json` — pinned machine-readable contract copy;
- `verified_action_core_adapter.py` — maps Stripe benchmark evidence into that contract;
- `test_verified_action_core_adapter.py` — offline fail-closed contract test.

The adapter **does not copy the Core decision engine** and does not claim
`CORE_VERIFIED`. Its output status is:

`VERIFIED_ACTION_CORE_CONTRACT_EXPORT_NOT_CORE_VERIFIED`

This is deliberate. The current Stripe P0-4A benchmark does not yet prove all
assurances required by the Core. In particular:

- the mandate is hash-bound but not cryptographically verified as a signed payment mandate;
- the run-level workflow confirmation is not an action-specific payment Human Gate;
- the benchmark receipt currently has `signature=null`;
- the receipt does not bind a first-class canonical scope;
- the receipt does not bind the exact execution request reference;
- several executed paths do not prove an execution-time authority re-check;
- several executed paths do not carry an idempotency/deduplication reference.

The adapter exports those gaps instead of filling them with assumptions.

## Evidence

The live workflow emits two files:

- `vdb-live-stripe-evidence.json` — original P0-4A benchmark evidence;
- `vdb-live-stripe-verified-action-core.json` — the same evidence mapped into the
  pinned Verified Action Core contract.

Both are uploaded in the same 90-day Actions artifact.

These artifacts remain **candidates**, not published benchmark results and not
proof of production payment authority. Publication still requires independent
repeatability, durable raw evidence, deterministic result-bundle validation and
a separate Human Gate. Production payment execution is outside this P0 scope.

## P0-4C signed-action contract (offline cryptographic gate)

The next promotion gate adds cryptographic authority semantics without adding a
second payment executor.

Files:

- `requirements-signed-action.txt` — isolated benchmark-only crypto dependency;
- `signed_action.py` — canonical Stripe sandbox action, Ed25519 mandate and
  role-separated receipt primitives, run-local replay gate;
- `test_signed_action.py` — fail-closed tamper, wrong-human-confirmation,
  replay, wrong-execution and signer-role tests.

The contract binds a payment mandate to:

- exact principal;
- canonical action hash;
- canonical scope;
- policy hash;
- action-specific human-confirmation digest;
- issue/expiry window;
- single-use nonce.

The completion receipt binds:

- action hash and scope;
- mandate;
- policy;
- principal;
- exact execution request;
- deduplication reference;
- system-of-record reference;
- verification source;
- observed-state digest.

This P0-4C slice is intentionally **offline only**. It does not add a new
Stripe API caller and does not move even sandbox value by itself. Existing
P0-4A remains the only Stripe sandbox execution harness.

The signing keys used by the tests are ephemeral benchmark keys generated in
memory. Passing these tests proves contract cryptography and binding semantics,
not a production trust root, durable replay ledger, workload identity, or an
authoritative `agentops-core` decision receipt.
