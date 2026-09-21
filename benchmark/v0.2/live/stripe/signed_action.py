from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


def canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def digest(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + sha256(raw).hexdigest()


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


@dataclass(frozen=True)
class SigningIdentity:
    key_id: str
    private_key: Ed25519PrivateKey

    @classmethod
    def generate(cls, key_id: str) -> "SigningIdentity":
        if not key_id.strip():
            raise ValueError("key_id required")
        return cls(key_id=key_id, private_key=Ed25519PrivateKey.generate())

    def public_key_b64(self) -> str:
        raw = self.private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return base64.b64encode(raw).decode("ascii")

    def sign(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        signature = self.private_key.sign(canonical_bytes(payload))
        return {
            "key_id": self.key_id,
            "payload": dict(payload),
            "signature_b64": base64.b64encode(signature).decode("ascii"),
        }


def verify_envelope(
    envelope: Mapping[str, Any],
    *,
    public_keys: Mapping[str, str],
) -> bool:
    key_id = str(envelope.get("key_id") or "")
    public_key_b64 = public_keys.get(key_id)
    if not public_key_b64:
        return False
    payload = envelope.get("payload")
    signature_b64 = str(envelope.get("signature_b64") or "")
    if not isinstance(payload, dict) or not signature_b64:
        return False
    try:
        public_key = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(public_key_b64)
        )
        public_key.verify(
            base64.b64decode(signature_b64),
            canonical_bytes(payload),
        )
        return True
    except (ValueError, InvalidSignature):
        return False


class ReplayLedger:
    """Run-local single-use gate.

    This proves replay handling inside one benchmark run only. It is not durable
    production replay state.
    """

    def __init__(self) -> None:
        self._seen: set[str] = set()

    def check_clear(self, ref: str) -> bool:
        return bool(ref) and ref not in self._seen

    def consume(self, ref: str) -> bool:
        if not self.check_clear(ref):
            return False
        self._seen.add(ref)
        return True


def canonical_payment_action(
    *,
    amount_minor: int,
    currency: str,
    payment_method_ref: str,
    merchant_account_digest: str,
) -> dict[str, Any]:
    if amount_minor <= 0:
        raise ValueError("amount_minor must be positive")
    return {
        "type": "stripe.sandbox.payment_intent.confirm",
        "provider": "stripe",
        "provider_surface": "PaymentIntents API",
        "environment": "sandbox",
        "amount_minor": int(amount_minor),
        "currency": str(currency).lower(),
        "payment_method_ref": str(payment_method_ref),
        "counterparty_ref": str(merchant_account_digest),
    }


def action_scope_ref(action: Mapping[str, Any]) -> str:
    return digest(
        {
            "type": action.get("type"),
            "environment": action.get("environment"),
            "amount_minor": action.get("amount_minor"),
            "currency": action.get("currency"),
            "payment_method_ref": action.get("payment_method_ref"),
            "counterparty_ref": action.get("counterparty_ref"),
        }
    )


def build_mandate_payload(
    *,
    mandate_id: str,
    principal_ref: str,
    action: Mapping[str, Any],
    policy_hash: str,
    human_confirmation_digest: str,
    issued_at: str,
    expires_at: str,
    nonce: str,
) -> dict[str, Any]:
    return {
        "kind": "PAYMENT_MANDATE",
        "version": "p0-4c",
        "mandate_id": mandate_id,
        "principal_ref": principal_ref,
        "action_hash": digest(action),
        "scope_ref": action_scope_ref(action),
        "policy_hash": policy_hash,
        "human_confirmation_digest": human_confirmation_digest,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "nonce": nonce,
        "single_use": True,
    }


def verify_payment_mandate(
    envelope: Mapping[str, Any],
    *,
    public_keys: Mapping[str, str],
    expected_principal_ref: str,
    expected_action: Mapping[str, Any],
    expected_policy_hash: str,
    expected_human_confirmation_digest: str,
    at: str,
    replay_ledger: ReplayLedger,
    consume: bool,
) -> tuple[bool, tuple[str, ...]]:
    reasons: list[str] = []
    if not verify_envelope(envelope, public_keys=public_keys):
        reasons.append("mandate_signature_invalid")

    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        return False, tuple(dict.fromkeys(reasons + ["mandate_payload_invalid"]))

    if payload.get("kind") != "PAYMENT_MANDATE":
        reasons.append("mandate_kind_mismatch")
    if payload.get("principal_ref") != expected_principal_ref:
        reasons.append("principal_mismatch")
    if payload.get("action_hash") != digest(expected_action):
        reasons.append("action_hash_mismatch")
    if payload.get("scope_ref") != action_scope_ref(expected_action):
        reasons.append("scope_mismatch")
    if payload.get("policy_hash") != expected_policy_hash:
        reasons.append("policy_hash_mismatch")
    if (
        payload.get("human_confirmation_digest")
        != expected_human_confirmation_digest
    ):
        reasons.append("human_confirmation_mismatch")
    if payload.get("single_use") is not True:
        reasons.append("single_use_required")

    try:
        now = parse_time(at)
        issued = parse_time(str(payload.get("issued_at") or ""))
        expires = parse_time(str(payload.get("expires_at") or ""))
        if not (issued <= now <= expires):
            reasons.append("mandate_not_active")
    except (TypeError, ValueError):
        reasons.append("mandate_time_invalid")

    replay_ref = str(payload.get("nonce") or payload.get("mandate_id") or "")
    if not replay_ledger.check_clear(replay_ref):
        reasons.append("replay_detected")

    if reasons:
        return False, tuple(dict.fromkeys(reasons))

    if consume and not replay_ledger.consume(replay_ref):
        return False, ("replay_detected",)

    return True, ()


def build_receipt_payload(
    *,
    receipt_id: str,
    principal_ref: str,
    mandate_id: str,
    action: Mapping[str, Any],
    policy_hash: str,
    execution_request_ref: str,
    execution_deduplication_ref: str,
    system_of_record_ref: str,
    verification_source_ref: str,
    observed_state_digest: str,
    issued_at: str,
) -> dict[str, Any]:
    return {
        "kind": "PAYMENT_COMPLETION_RECEIPT",
        "version": "p0-4c",
        "receipt_id": receipt_id,
        "principal_ref": principal_ref,
        "mandate_id": mandate_id,
        "action_hash": digest(action),
        "scope_ref": action_scope_ref(action),
        "policy_hash": policy_hash,
        "execution_request_ref": execution_request_ref,
        "execution_deduplication_ref": execution_deduplication_ref,
        "system_of_record_ref": system_of_record_ref,
        "verification_source_ref": verification_source_ref,
        "observed_state_digest": observed_state_digest,
        "issued_at": issued_at,
        "outcome": "VERIFIED_SUCCESS",
    }


def verify_payment_receipt(
    envelope: Mapping[str, Any],
    *,
    public_keys: Mapping[str, str],
    mandate_signer_key_id: str,
    expected_principal_ref: str,
    expected_mandate_id: str,
    expected_action: Mapping[str, Any],
    expected_policy_hash: str,
    expected_execution_request_ref: str,
    expected_execution_deduplication_ref: str,
    expected_system_of_record_ref: str,
    expected_verification_source_ref: str,
    expected_observed_state_digest: str,
) -> tuple[bool, tuple[str, ...]]:
    reasons: list[str] = []
    if str(envelope.get("key_id") or "") == mandate_signer_key_id:
        reasons.append("receipt_signer_not_role_separated")
    if not verify_envelope(envelope, public_keys=public_keys):
        reasons.append("receipt_signature_invalid")

    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        return False, tuple(dict.fromkeys(reasons + ["receipt_payload_invalid"]))

    expected = {
        "kind": "PAYMENT_COMPLETION_RECEIPT",
        "principal_ref": expected_principal_ref,
        "mandate_id": expected_mandate_id,
        "action_hash": digest(expected_action),
        "scope_ref": action_scope_ref(expected_action),
        "policy_hash": expected_policy_hash,
        "execution_request_ref": expected_execution_request_ref,
        "execution_deduplication_ref": expected_execution_deduplication_ref,
        "system_of_record_ref": expected_system_of_record_ref,
        "verification_source_ref": expected_verification_source_ref,
        "observed_state_digest": expected_observed_state_digest,
        "outcome": "VERIFIED_SUCCESS",
    }
    for key, expected_value in expected.items():
        if payload.get(key) != expected_value:
            reasons.append(f"receipt_{key}_mismatch")

    return not reasons, tuple(dict.fromkeys(reasons))
