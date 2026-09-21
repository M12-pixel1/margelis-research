from __future__ import annotations

from datetime import datetime, timedelta, timezone

from signed_action import (
    ReplayLedger,
    SigningIdentity,
    action_scope_ref,
    build_mandate_payload,
    build_receipt_payload,
    canonical_payment_action,
    digest,
    verify_payment_mandate,
    verify_payment_receipt,
)


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _fixture():
    now = datetime.now(timezone.utc)
    action = canonical_payment_action(
        amount_minor=123,
        currency="eur",
        payment_method_ref="pm_card_visa",
        merchant_account_digest="sha256:merchant",
    )
    mandate_signer = SigningIdentity.generate("benchmark-mandate-key")
    receipt_signer = SigningIdentity.generate("benchmark-receipt-key")
    keys = {
        mandate_signer.key_id: mandate_signer.public_key_b64(),
        receipt_signer.key_id: receipt_signer.public_key_b64(),
    }
    principal = "principal:margelis-benchmark-human"
    policy_hash = digest({"policy": "stripe-signed-p0-4c-v1"})
    human_digest = digest("AUTHORIZE_STRIPE_SANDBOX_123_EUR_PM_CARD_VISA_ONCE")
    mandate_payload = build_mandate_payload(
        mandate_id="mandate:p0-4c:test",
        principal_ref=principal,
        action=action,
        policy_hash=policy_hash,
        human_confirmation_digest=human_digest,
        issued_at=_iso(now - timedelta(seconds=5)),
        expires_at=_iso(now + timedelta(minutes=5)),
        nonce="nonce:p0-4c:test",
    )
    mandate = mandate_signer.sign(mandate_payload)
    return {
        "now": now,
        "action": action,
        "mandate_signer": mandate_signer,
        "receipt_signer": receipt_signer,
        "keys": keys,
        "principal": principal,
        "policy_hash": policy_hash,
        "human_digest": human_digest,
        "mandate": mandate,
    }


def main() -> None:
    fx = _fixture()
    ledger = ReplayLedger()

    ok, reasons = verify_payment_mandate(
        fx["mandate"],
        public_keys=fx["keys"],
        expected_principal_ref=fx["principal"],
        expected_action=fx["action"],
        expected_policy_hash=fx["policy_hash"],
        expected_human_confirmation_digest=fx["human_digest"],
        at=_iso(fx["now"]),
        replay_ledger=ledger,
        consume=False,
    )
    assert ok, reasons

    # The execution-time verification consumes single-use authority.
    ok, reasons = verify_payment_mandate(
        fx["mandate"],
        public_keys=fx["keys"],
        expected_principal_ref=fx["principal"],
        expected_action=fx["action"],
        expected_policy_hash=fx["policy_hash"],
        expected_human_confirmation_digest=fx["human_digest"],
        at=_iso(fx["now"]),
        replay_ledger=ledger,
        consume=True,
    )
    assert ok, reasons

    ok, reasons = verify_payment_mandate(
        fx["mandate"],
        public_keys=fx["keys"],
        expected_principal_ref=fx["principal"],
        expected_action=fx["action"],
        expected_policy_hash=fx["policy_hash"],
        expected_human_confirmation_digest=fx["human_digest"],
        at=_iso(fx["now"]),
        replay_ledger=ledger,
        consume=True,
    )
    assert not ok and "replay_detected" in reasons

    tampered = {
        **fx["mandate"],
        "payload": {**fx["mandate"]["payload"], "principal_ref": "principal:other"},
    }
    ok, reasons = verify_payment_mandate(
        tampered,
        public_keys=fx["keys"],
        expected_principal_ref=fx["principal"],
        expected_action=fx["action"],
        expected_policy_hash=fx["policy_hash"],
        expected_human_confirmation_digest=fx["human_digest"],
        at=_iso(fx["now"]),
        replay_ledger=ReplayLedger(),
        consume=False,
    )
    assert not ok and "mandate_signature_invalid" in reasons

    wrong_human = digest("WRONG")
    ok, reasons = verify_payment_mandate(
        fx["mandate"],
        public_keys=fx["keys"],
        expected_principal_ref=fx["principal"],
        expected_action=fx["action"],
        expected_policy_hash=fx["policy_hash"],
        expected_human_confirmation_digest=wrong_human,
        at=_iso(fx["now"]),
        replay_ledger=ReplayLedger(),
        consume=False,
    )
    assert not ok and "human_confirmation_mismatch" in reasons

    receipt_payload = build_receipt_payload(
        receipt_id="receipt:p0-4c:test",
        principal_ref=fx["principal"],
        mandate_id=fx["mandate"]["payload"]["mandate_id"],
        action=fx["action"],
        policy_hash=fx["policy_hash"],
        execution_request_ref="stripe-request:req_test",
        execution_deduplication_ref="idem:test",
        system_of_record_ref="stripe:pi_test",
        verification_source_ref="stripe-api:GET-payment_intent",
        observed_state_digest="sha256:readback",
        issued_at=_iso(fx["now"]),
    )
    receipt = fx["receipt_signer"].sign(receipt_payload)

    ok, reasons = verify_payment_receipt(
        receipt,
        public_keys=fx["keys"],
        mandate_signer_key_id=fx["mandate_signer"].key_id,
        expected_principal_ref=fx["principal"],
        expected_mandate_id=fx["mandate"]["payload"]["mandate_id"],
        expected_action=fx["action"],
        expected_policy_hash=fx["policy_hash"],
        expected_execution_request_ref="stripe-request:req_test",
        expected_execution_deduplication_ref="idem:test",
        expected_system_of_record_ref="stripe:pi_test",
        expected_verification_source_ref="stripe-api:GET-payment_intent",
        expected_observed_state_digest="sha256:readback",
    )
    assert ok, reasons

    wrong_exec = fx["receipt_signer"].sign(
        {**receipt_payload, "execution_request_ref": "stripe-request:req_other"}
    )
    ok, reasons = verify_payment_receipt(
        wrong_exec,
        public_keys=fx["keys"],
        mandate_signer_key_id=fx["mandate_signer"].key_id,
        expected_principal_ref=fx["principal"],
        expected_mandate_id=fx["mandate"]["payload"]["mandate_id"],
        expected_action=fx["action"],
        expected_policy_hash=fx["policy_hash"],
        expected_execution_request_ref="stripe-request:req_test",
        expected_execution_deduplication_ref="idem:test",
        expected_system_of_record_ref="stripe:pi_test",
        expected_verification_source_ref="stripe-api:GET-payment_intent",
        expected_observed_state_digest="sha256:readback",
    )
    assert not ok and "receipt_execution_request_ref_mismatch" in reasons

    same_role_receipt = fx["mandate_signer"].sign(receipt_payload)
    ok, reasons = verify_payment_receipt(
        same_role_receipt,
        public_keys=fx["keys"],
        mandate_signer_key_id=fx["mandate_signer"].key_id,
        expected_principal_ref=fx["principal"],
        expected_mandate_id=fx["mandate"]["payload"]["mandate_id"],
        expected_action=fx["action"],
        expected_policy_hash=fx["policy_hash"],
        expected_execution_request_ref="stripe-request:req_test",
        expected_execution_deduplication_ref="idem:test",
        expected_system_of_record_ref="stripe:pi_test",
        expected_verification_source_ref="stripe-api:GET-payment_intent",
        expected_observed_state_digest="sha256:readback",
    )
    assert not ok and "receipt_signer_not_role_separated" in reasons

    assert action_scope_ref(fx["action"]).startswith("sha256:")
    print("stripe_signed_action: PASS")


if __name__ == "__main__":
    main()
