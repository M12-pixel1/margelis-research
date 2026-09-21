from __future__ import annotations

import json
import os
from hashlib import sha256
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


HERE = Path(__file__).resolve().parent
SCHEMA_PATH = HERE / "verified_action_core_v0.1.schema.json"
PIN_PATH = HERE / "verified_action_core_pin.json"

DEFAULT_INPUT = Path(
    os.environ.get("VDB_EVIDENCE_PATH", "vdb-live-stripe-evidence.json")
)
DEFAULT_OUTPUT = Path(
    os.environ.get(
        "MARGELIS_VAC_EVIDENCE_PATH",
        "vdb-live-stripe-verified-action-core.json",
    )
)


def digest(value: Any) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return "sha256:" + sha256(raw).hexdigest()


def _evidence_value(row: dict[str, Any], key: str) -> Any:
    for item in row.get("evidence") or []:
        if isinstance(item, dict) and key in item:
            return item[key]
    return None


def _action_scope(row: dict[str, Any]) -> str:
    receipt = row["receipt"]
    action = receipt.get("requested_action") or {}
    return digest(
        {
            "provider": "stripe",
            "provider_surface": "PaymentIntents API",
            "scenario": row.get("scenario"),
            "action": action,
        }
    )


def _mandate_active_at_execution(row: dict[str, Any]) -> bool:
    return row.get("scenario") not in {
        "expired_mandate",
        "toctou_authority_revocation",
    }


def _replay_clear(row: dict[str, Any]) -> bool:
    return row.get("scenario") != "replay"


def _authority_rechecked(row: dict[str, Any]) -> bool:
    return (
        row.get("system") == "guarded"
        and row.get("scenario")
        in {"expired_mandate", "toctou_authority_revocation"}
    )


def _execution_request_ref(row: dict[str, Any]) -> str | None:
    direct = _evidence_value(row, "stripe_create_request_id")
    if direct:
        return f"stripe-request:{direct}"

    request_ids = _evidence_value(row, "stripe_request_ids")
    if isinstance(request_ids, list) and len(request_ids) == 1 and request_ids[0]:
        return f"stripe-request:{request_ids[0]}"

    return None


def _deduplication_ref(row: dict[str, Any]) -> str | None:
    value = _evidence_value(row, "idempotency_key_digest")
    if value:
        return str(value)
    return None


def build_authorization(row: dict[str, Any]) -> dict[str, Any]:
    receipt = row["receipt"]
    action = receipt.get("requested_action") or {}
    executed = receipt.get("executed_action") is not None

    return {
        "actor_ref": str(receipt.get("executor_identity") or ""),
        "principal_ref": str(receipt.get("principal_id") or ""),
        "action_type": str(action.get("type") or ""),
        "action_hash": digest(action),
        "scope_ref": _action_scope(row),
        "identity_verified": bool(receipt.get("executor_identity")),
        "mandate_ref": receipt.get("mandate_id"),
        # Current P0-4A receipts carry a mandate hash, not a verified signature.
        "mandate_authenticity_verified": False,
        "mandate_scope_matches": True,
        "mandate_active_at_execution": _mandate_active_at_execution(row),
        "replay_clear_before_execution": _replay_clear(row),
        "policy_hash": receipt.get("policy_hash"),
        "policy_allows_action": receipt.get("authorization_decision") == "ALLOW",
        "policy_hash_continuity": True,
        # Payment is a regulated financial action under AgentOps constitutional rules.
        "regulated_action": True,
        "human_gate_required": True,
        # RUN_STRIPE_P0_4A authorizes the benchmark run. It is not an
        # action-specific principal payment mandate and must not be promoted as one.
        "human_gate_satisfied": False,
        "authority_rechecked_immediately_before_execution": _authority_rechecked(
            row
        ),
        "material_external_action": executed,
        "execution_deduplication_ref": (
            _deduplication_ref(row) if executed else None
        ),
    }


def build_completion(
    row: dict[str, Any],
    authorization: dict[str, Any],
) -> dict[str, Any] | None:
    receipt = row["receipt"]
    if receipt.get("executed_action") is None:
        return None

    verifier = str(receipt.get("verification_source") or "")
    independent_provider_readback = verifier.startswith("stripe-api:")
    externally_verified_success = (
        independent_provider_readback
        and receipt.get("outcome_status") == "VERIFIED_SUCCESS"
    )

    return {
        "authorization": authorization,
        "execution_request_ref": _execution_request_ref(row),
        "system_of_record_ref": receipt.get("external_state_reference"),
        "verification_source_ref": verifier or None,
        "outcome_verified": externally_verified_success,
        "receipt_ref": receipt.get("receipt_id"),
        # P0-4A benchmark receipt schema currently has signature=null.
        "receipt_authenticity_verified": False,
        # The receipt carries the requested action, but scope and exact execution
        # request are not first-class signed bindings in P0-4A.
        "receipt_binds_action_hash": bool(receipt.get("requested_action")),
        "receipt_binds_scope": False,
        "receipt_binds_mandate": bool(receipt.get("mandate_id")),
        "receipt_binds_policy": bool(receipt.get("policy_hash")),
        "receipt_binds_principal": bool(receipt.get("principal_id")),
        "receipt_binds_execution": False,
    }


def build_contract(row: dict[str, Any]) -> dict[str, Any]:
    authorization = build_authorization(row)
    contract = {
        "contract_version": "0.1",
        "authorization": authorization,
        "completion": build_completion(row, authorization),
    }
    validate_contract(contract)
    return contract


def validate_contract(contract: dict[str, Any]) -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = sorted(
        error.message
        for error in Draft202012Validator(
            schema,
            format_checker=FormatChecker(),
        ).iter_errors(contract)
    )
    if errors:
        raise RuntimeError(
            "Verified Action Core contract schema validation failed: "
            + "; ".join(errors)
        )


def known_missing_assurances(
    contract: dict[str, Any],
) -> list[str]:
    authorization = contract["authorization"]
    missing: list[str] = []

    for key in (
        "mandate_authenticity_verified",
        "mandate_scope_matches",
        "mandate_active_at_execution",
        "replay_clear_before_execution",
        "policy_allows_action",
        "policy_hash_continuity",
        "human_gate_satisfied",
        "authority_rechecked_immediately_before_execution",
    ):
        if not authorization[key]:
            missing.append(key)

    if (
        authorization["material_external_action"]
        and not authorization["execution_deduplication_ref"]
    ):
        missing.append("execution_deduplication_ref")

    completion = contract["completion"]
    if completion is not None:
        for key in (
            "execution_request_ref",
            "system_of_record_ref",
            "verification_source_ref",
            "outcome_verified",
            "receipt_ref",
            "receipt_authenticity_verified",
            "receipt_binds_action_hash",
            "receipt_binds_scope",
            "receipt_binds_mandate",
            "receipt_binds_policy",
            "receipt_binds_principal",
            "receipt_binds_execution",
        ):
            if not completion[key]:
                missing.append(key)

    return sorted(set(missing))


def export_document(source: dict[str, Any]) -> dict[str, Any]:
    if source.get("sandbox_only") is not True:
        raise RuntimeError(
            "REFUSED: Verified Action Core Stripe adapter accepts sandbox evidence only"
        )

    pin = json.loads(PIN_PATH.read_text(encoding="utf-8"))
    rows = []

    for row in source.get("rows") or []:
        contract = build_contract(row)
        rows.append(
            {
                "scenario": row.get("scenario"),
                "system": row.get("system"),
                "source_benchmark_pass": bool(row.get("pass")),
                "source_expected": row.get("expected"),
                "adapter_status": "CONTRACT_VALID_NOT_CORE_VERIFIED",
                "known_missing_assurances": known_missing_assurances(contract),
                "contract": contract,
            }
        )

    return {
        "status": "VERIFIED_ACTION_CORE_CONTRACT_EXPORT_NOT_CORE_VERIFIED",
        "core_pin": pin,
        "source": {
            "benchmark": source.get("benchmark"),
            "provider": source.get("provider"),
            "provider_surface": source.get("provider_surface"),
            "sandbox_only": True,
            "run_id": source.get("run_id"),
            "stripe_account_id_digest": source.get("stripe_account_id_digest"),
        },
        "rows": rows,
        "claims": {
            "schema_validated": True,
            "core_decision_executed": False,
            "production_payment_authority": False,
            "real_money_moved": False,
        },
        "limitations": [
            "This adapter exports evidence into the pinned Verified Action Core contract; it does not copy or execute the Core decision engine.",
            "The Stripe P0-4A benchmark currently lacks cryptographically verified payment mandates and signed action-bound completion receipts.",
            "The workflow-level RUN_STRIPE_P0_4A confirmation is not treated as an action-specific payment Human Gate.",
            "Stripe sandbox PaymentIntents do not move real money.",
        ],
    }


def run(
    input_path: Path = DEFAULT_INPUT,
    output_path: Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    source = json.loads(input_path.read_text(encoding="utf-8"))
    document = export_document(source)
    output_path.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": document["status"],
                "rows": len(document["rows"]),
                "core_decision_executed": False,
            },
            sort_keys=True,
        )
    )
    print(f"evidence={output_path}")
    return document


if __name__ == "__main__":
    run()
