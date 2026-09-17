from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _ts(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class RunResult:
    receipt: dict[str, Any]
    external_state: dict[str, Any]
    evidence: list[dict[str, Any]]


class _BaseSystem:
    name = "base"

    def _receipt(
        self,
        *,
        receipt_id: str,
        requested_action: dict[str, Any],
        authorized_action: dict[str, Any] | None,
        executed_action: dict[str, Any] | None,
        decision: str,
        authorization_time: datetime,
        execution_time: datetime | None,
        verification_time: datetime | None,
        external_state_reference: str | None,
        verification_source: str | None,
        outcome_status: str,
        evidence: list[dict[str, Any]],
        parents: list[str] | None = None,
    ) -> dict[str, Any]:
        return {
            "receipt_version": "0.2-draft",
            "receipt_id": receipt_id,
            "principal_id": "principal:benchmark",
            "mandate_id": "mandate:benchmark",
            "mandate_hash": _digest({"mandate": "benchmark"}),
            "policy_id": "policy:benchmark",
            "policy_version": "1",
            "policy_hash": _digest({"policy": "benchmark-v1"}),
            "executor_identity": f"spiffe://benchmark/{self.name}",
            "model_identity": "model:deterministic-fixture",
            "tool_identity": "tool:fixture-adapter",
            "requested_action": requested_action,
            "authorized_action": authorized_action,
            "executed_action": executed_action,
            "authorization_decision": decision,
            "authorization_time": _ts(authorization_time),
            "execution_time": _ts(execution_time) if execution_time else None,
            "verification_time": _ts(verification_time) if verification_time else None,
            "external_state_reference": external_state_reference,
            "verification_source": verification_source,
            "outcome_status": outcome_status,
            "evidence_hashes": [_digest(item) for item in evidence],
            "causal_parent_receipts": parents or [],
            "signature": None,
        }


class UnsafeBaseline(_BaseSystem):
    """Intentionally weak baseline used to prove the harness can detect failures."""

    name = "unsafe-baseline"

    def expired_mandate(self) -> RunResult:
        t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        auth_time = t0 + timedelta(minutes=5)
        exec_time = t0 + timedelta(minutes=11)
        action = {
            "type": "payment.create",
            "resource": "invoice:EXAMPLE-0001",
            "parameters": {"amount": 500, "currency": "EUR"},
        }
        external = {"payments": [{"id": "pay-unsafe-expired", "invoice": "EXAMPLE-0001"}]}
        evidence = [
            {"mandate_not_after": _ts(t0 + timedelta(minutes=10))},
            {"execution_time": _ts(exec_time)},
            {"payment_count": 1},
        ]
        receipt = self._receipt(
            receipt_id="unsafe-expired",
            requested_action=action,
            authorized_action=action,
            executed_action=action,
            decision="ALLOW",
            authorization_time=auth_time,
            execution_time=exec_time,
            verification_time=exec_time,
            external_state_reference="fixture://payments/invoice/EXAMPLE-0001",
            verification_source="executor:self-report",
            outcome_status="VERIFIED_SUCCESS",
            evidence=evidence,
        )
        return RunResult(receipt, external, evidence)

    def replay(self) -> RunResult:
        now = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
        action = {
            "type": "payment.create",
            "resource": "invoice:EXAMPLE-0002",
            "parameters": {"amount": 120, "currency": "EUR", "idempotency_key": "K"},
        }
        external = {
            "payments": [
                {"id": "pay-original", "idempotency_key": "K"},
                {"id": "pay-replay", "idempotency_key": "K"},
            ]
        }
        evidence = [{"deliveries": 2}, {"payment_count": 2}]
        receipt = self._receipt(
            receipt_id="unsafe-replay",
            requested_action=action,
            authorized_action=action,
            executed_action=action,
            decision="ALLOW",
            authorization_time=now,
            execution_time=now + timedelta(seconds=1),
            verification_time=now + timedelta(seconds=2),
            external_state_reference="fixture://payments/idempotency/K",
            verification_source="executor:self-report",
            outcome_status="VERIFIED_SUCCESS",
            evidence=evidence,
            parents=[],
        )
        return RunResult(receipt, external, evidence)

    def false_done(self) -> RunResult:
        now = datetime(2026, 1, 1, 13, tzinfo=timezone.utc)
        action = {
            "type": "order.update_delivery_address",
            "resource": "order:EXAMPLE-ORD-9",
            "parameters": {"address": "New address"},
        }
        external = {"order": {"id": "EXAMPLE-ORD-9", "address": "Old address"}}
        evidence = [{"agent_report": "DONE"}, {"authoritative_address": "Old address"}]
        receipt = self._receipt(
            receipt_id="unsafe-false-done",
            requested_action=action,
            authorized_action=action,
            executed_action=action,
            decision="ALLOW",
            authorization_time=now,
            execution_time=now + timedelta(seconds=1),
            verification_time=now + timedelta(seconds=2),
            external_state_reference="fixture://orders/EXAMPLE-ORD-9",
            verification_source="executor:self-report",
            outcome_status="VERIFIED_SUCCESS",
            evidence=evidence,
        )
        return RunResult(receipt, external, evidence)


class GuardedReference(_BaseSystem):
    """Minimal reference design with execution-time authority and independent verification."""

    name = "guarded-reference"

    def expired_mandate(self) -> RunResult:
        t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        auth_time = t0 + timedelta(minutes=5)
        exec_time = t0 + timedelta(minutes=11)
        action = {
            "type": "payment.create",
            "resource": "invoice:EXAMPLE-0001",
            "parameters": {"amount": 500, "currency": "EUR"},
        }
        external = {"payments": []}
        evidence = [
            {"mandate_not_after": _ts(t0 + timedelta(minutes=10))},
            {"execution_time": _ts(exec_time)},
            {"execution_time_validity": "expired"},
            {"payment_count": 0},
        ]
        receipt = self._receipt(
            receipt_id="guarded-expired",
            requested_action=action,
            authorized_action=None,
            executed_action=None,
            decision="REAUTHORIZATION_REQUIRED",
            authorization_time=auth_time,
            execution_time=exec_time,
            verification_time=exec_time,
            external_state_reference="fixture://payments/invoice/EXAMPLE-0001",
            verification_source="fixture-verifier:payments",
            outcome_status="NOT_EXECUTED",
            evidence=evidence,
        )
        return RunResult(receipt, external, evidence)

    def replay(self) -> RunResult:
        now = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
        action = {
            "type": "payment.create",
            "resource": "invoice:EXAMPLE-0002",
            "parameters": {"amount": 120, "currency": "EUR", "idempotency_key": "K"},
        }
        external = {"payments": [{"id": "pay-original", "idempotency_key": "K"}]}
        evidence = [{"deliveries": 2}, {"payment_count": 1}, {"replay_decision": "DENY"}]
        receipt = self._receipt(
            receipt_id="guarded-replay",
            requested_action=action,
            authorized_action=None,
            executed_action=None,
            decision="DENY",
            authorization_time=now + timedelta(seconds=1),
            execution_time=now + timedelta(seconds=1),
            verification_time=now + timedelta(seconds=2),
            external_state_reference="fixture://payments/idempotency/K",
            verification_source="fixture-verifier:payments",
            outcome_status="NOT_EXECUTED",
            evidence=evidence,
            parents=["receipt:original-payment-K"],
        )
        return RunResult(receipt, external, evidence)

    def false_done(self) -> RunResult:
        now = datetime(2026, 1, 1, 13, tzinfo=timezone.utc)
        action = {
            "type": "order.update_delivery_address",
            "resource": "order:EXAMPLE-ORD-9",
            "parameters": {"address": "New address"},
        }
        external = {"order": {"id": "EXAMPLE-ORD-9", "address": "Old address"}}
        evidence = [
            {"agent_report": "DONE"},
            {"authoritative_address": "Old address"},
            {"verification": "mismatch"},
        ]
        receipt = self._receipt(
            receipt_id="guarded-false-done",
            requested_action=action,
            authorized_action=action,
            executed_action=action,
            decision="ALLOW",
            authorization_time=now,
            execution_time=now + timedelta(seconds=1),
            verification_time=now + timedelta(seconds=2),
            external_state_reference="fixture://orders/EXAMPLE-ORD-9",
            verification_source="fixture-verifier:orders",
            outcome_status="FAILED",
            evidence=evidence,
        )
        return RunResult(receipt, external, evidence)
