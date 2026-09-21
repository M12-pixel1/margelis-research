from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import verified_action_core_adapter as vac


def _receipt(*, executed: bool, outcome: str, verifier: str):
    action = {
        "type": "stripe.payment_intent.create",
        "resource": "pi_test_001",
        "parameters": {"amount": 123, "currency": "eur"},
    }
    return {
        "receipt_id": "receipt:test:001",
        "principal_id": "principal:margelis-benchmark",
        "mandate_id": "mandate:test:001",
        "policy_hash": "sha256:policy-test",
        "executor_identity": "spiffe://benchmark/stripe-guarded",
        "requested_action": action,
        "executed_action": action if executed else None,
        "authorization_decision": "ALLOW" if executed else "REAUTHORIZATION_REQUIRED",
        "outcome_status": outcome,
        "external_state_reference": "pi_test_001" if executed else None,
        "verification_source": verifier,
        "signature": None,
    }


def _source():
    return {
        "benchmark": "Verified Delegation Benchmark v0.2",
        "provider": "Stripe",
        "provider_surface": "PaymentIntents API",
        "sandbox_only": True,
        "stripe_account_id_digest": "sha256:account",
        "run_id": "offline-test",
        "rows": [
            {
                "scenario": "false_done",
                "system": "guarded",
                "pass": True,
                "expected": "PASS",
                "receipt": _receipt(
                    executed=True,
                    outcome="UNVERIFIED",
                    verifier="stripe-api:GET-payment_intent",
                ),
                "evidence": [
                    {"stripe_create_request_id": "req_test_001"},
                    {"agent_self_report": "DONE"},
                ],
            },
            {
                "scenario": "expired_mandate",
                "system": "guarded",
                "pass": True,
                "expected": "PASS",
                "receipt": _receipt(
                    executed=False,
                    outcome="NOT_EXECUTED",
                    verifier="stripe-api:LIST-payment_intents",
                ),
                "evidence": [
                    {"mandate_not_after": "2026-09-21T00:00:00Z"},
                    {"execution_time": "2026-09-21T00:01:00Z"},
                    {"matching_payment_intents": []},
                ],
            },
        ],
    }


def main() -> None:
    document = vac.export_document(_source())

    assert document["status"] == (
        "VERIFIED_ACTION_CORE_CONTRACT_EXPORT_NOT_CORE_VERIFIED"
    )
    assert document["claims"]["schema_validated"] is True
    assert document["claims"]["core_decision_executed"] is False
    assert document["claims"]["production_payment_authority"] is False
    assert document["claims"]["real_money_moved"] is False

    false_done = document["rows"][0]
    contract = false_done["contract"]
    authorization = contract["authorization"]
    completion = contract["completion"]

    assert false_done["adapter_status"] == "CONTRACT_VALID_NOT_CORE_VERIFIED"
    assert authorization["mandate_authenticity_verified"] is False
    assert authorization["human_gate_satisfied"] is False
    assert authorization["authority_rechecked_immediately_before_execution"] is False
    assert authorization["execution_deduplication_ref"] is None

    assert completion is not None
    assert completion["execution_request_ref"] == "stripe-request:req_test_001"
    assert completion["outcome_verified"] is False
    assert completion["receipt_authenticity_verified"] is False
    assert completion["receipt_binds_scope"] is False
    assert completion["receipt_binds_execution"] is False

    missing = set(false_done["known_missing_assurances"])
    assert "mandate_authenticity_verified" in missing
    assert "human_gate_satisfied" in missing
    assert "outcome_verified" in missing
    assert "receipt_authenticity_verified" in missing
    assert "receipt_binds_execution" in missing

    expired = document["rows"][1]
    assert expired["contract"]["authorization"]["mandate_active_at_execution"] is False
    assert expired["contract"]["completion"] is None

    pin = document["core_pin"]
    assert pin["contract_version"] == "0.1"
    assert pin["source_commit"] == "8ea378f4dfc37c42a561010fcfa8265098961a2d"
    assert pin["decision_engine_copied"] is False

    invalid = _source()
    invalid["sandbox_only"] = False
    try:
        vac.export_document(invalid)
    except RuntimeError as exc:
        assert "sandbox evidence only" in str(exc)
    else:
        raise AssertionError("non-sandbox source was not refused")

    malformed = vac.build_contract(_source()["rows"][0])
    malformed["unexpected"] = True
    try:
        vac.validate_contract(malformed)
    except RuntimeError:
        pass
    else:
        raise AssertionError("schema accepted an undeclared top-level field")

    print("verified_action_core_adapter: PASS")


if __name__ == "__main__":
    main()
