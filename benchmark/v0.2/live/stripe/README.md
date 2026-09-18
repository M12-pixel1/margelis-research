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

## Evidence

The workflow emits `vdb-live-stripe-evidence.json` and uploads it as a
90-day Actions artifact. That artifact remains a **candidate**, not a published
benchmark result. Publication requires an independent repeat run, durable raw
evidence, the deterministic result-bundle validator, and a separate Human Gate.
