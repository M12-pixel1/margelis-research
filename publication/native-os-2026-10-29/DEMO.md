# Five-minute technical demonstration

Status: synthetic reference demonstration. No production actions or customer data.

1. Explain the boundary: an agent statement, tool acceptance and a verified external result are different observations. The demonstration uses two publisher-defined reference behaviours, not competing commercial agents.
2. Run the existing harness using REPRODUCE.md. Show the expired-mandate case: an old approval is present, but the synthetic action time is after expiry. Show payment count and authorization decision in the raw output.
3. Show replay: compare two deliveries against the final synthetic payment count. The guarded reference leaves one payment and identifies the denied replay's causal parent.
4. Show false completion: compare the claimed new address with the unchanged authoritative fixture. The guarded outcome is FAILED. A failure detected correctly is a passing safety check; it is not a successfully completed customer task.
5. Run the HTTP/SQLite sandbox and identify the separate state process and read-only verifier. Explain that process separation is not an independent organization or a real bank.
6. End with the three-scenario scope, two repeats per stage, raw files and unproven adapter integration. Invite a counterexample that distinguishes the proposed contract from the existing reference behaviours.

Never describe the fixture as a real payment, booking, clinical intervention or production Native OS execution. Do not present passing negative controls as additional customer successes.
