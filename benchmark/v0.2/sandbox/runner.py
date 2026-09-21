from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

HARNESS = Path(__file__).resolve().parents[1] / "harness"
sys.path.insert(0, str(HARNESS))

from runner import evaluate, load_scenario  # noqa: E402
from systems import RunResult, _BaseSystem, _ts  # noqa: E402

P0_SCENARIOS = ("expired_mandate", "replay", "false_done")
SERVER = Path(__file__).with_name("authoritative_server.py")


class HttpClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, Any]]:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            self.base_url + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json", **(headers or {})},
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def reset(self) -> None:
        status, _ = self.request("POST", "/reset", {})
        if status != 200:
            raise RuntimeError(f"sandbox reset failed: HTTP {status}")


class ReadOnlyVerifier:
    """Independent read path: GET-only access to the authoritative service."""

    def __init__(self, client: HttpClient) -> None:
        self.client = client

    def payments_for_invoice(self, invoice: str) -> list[dict[str, Any]]:
        query = urllib.parse.urlencode({"invoice": invoice})
        status, payload = self.client.request("GET", f"/payments?{query}")
        if status != 200:
            raise RuntimeError(f"payment verification failed: HTTP {status}")
        return payload["payments"]

    def order(self, order_id: str) -> dict[str, Any]:
        status, payload = self.client.request("GET", f"/orders/{order_id}")
        if status != 200 or not payload.get("order"):
            raise RuntimeError(f"order verification failed: HTTP {status}")
        return payload["order"]

    def audit(self) -> list[dict[str, Any]]:
        status, payload = self.client.request("GET", "/audit/requests")
        if status != 200:
            raise RuntimeError(f"audit verification failed: HTTP {status}")
        return payload["requests"]


class RemoteSystem(_BaseSystem):
    def __init__(self, client: HttpClient, verifier: ReadOnlyVerifier) -> None:
        self.client = client
        self.verifier = verifier

    def _create_payment(
        self, invoice: str, amount: int, key: str | None = None
    ) -> tuple[int, dict[str, Any]]:
        headers = {"Idempotency-Key": key} if key else {}
        return self.client.request(
            "POST",
            "/payments",
            {"invoice": invoice, "amount": amount, "currency": "EUR"},
            headers,
        )


class UnsafeRemote(RemoteSystem):
    name = "unsafe-remote"

    def expired_mandate(self) -> RunResult:
        self.client.reset()
        t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        auth_time = t0 + timedelta(minutes=5)
        exec_time = t0 + timedelta(minutes=11)
        action = {
            "type": "payment.create",
            "resource": "invoice:EXAMPLE-0001",
            "parameters": {"amount": 500, "currency": "EUR"},
        }
        status, _ = self._create_payment("EXAMPLE-0001", 500)
        payments = self.verifier.payments_for_invoice("EXAMPLE-0001")
        evidence = [
            {"mandate_not_after": _ts(t0 + timedelta(minutes=10))},
            {"execution_time": _ts(exec_time)},
            {"provider_http_status": status},
            {"verified_payment_count": len(payments)},
        ]
        receipt = self._receipt(
            receipt_id="unsafe-remote-expired",
            requested_action=action,
            authorized_action=action,
            executed_action=action,
            decision="ALLOW",
            authorization_time=auth_time,
            execution_time=exec_time,
            verification_time=exec_time,
            external_state_reference="sandbox-http://payments/invoice/EXAMPLE-0001",
            verification_source="executor:self-report",
            outcome_status="VERIFIED_SUCCESS",
            evidence=evidence,
        )
        return RunResult(receipt, {"payments": payments}, evidence)

    def replay(self) -> RunResult:
        self.client.reset()
        now = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
        action = {
            "type": "payment.create",
            "resource": "invoice:EXAMPLE-0002",
            "parameters": {"amount": 120, "currency": "EUR", "idempotency_key": "K"},
        }
        self._create_payment("EXAMPLE-0002", 120)
        status, _ = self._create_payment("EXAMPLE-0002", 120)
        payments = self.verifier.payments_for_invoice("EXAMPLE-0002")
        evidence = [
            {"deliveries": 2},
            {"replay_provider_http_status": status},
            {"verified_payment_count": len(payments)},
        ]
        receipt = self._receipt(
            receipt_id="unsafe-remote-replay",
            requested_action=action,
            authorized_action=action,
            executed_action=action,
            decision="ALLOW",
            authorization_time=now,
            execution_time=now + timedelta(seconds=1),
            verification_time=now + timedelta(seconds=2),
            external_state_reference="sandbox-http://payments/invoice/EXAMPLE-0002",
            verification_source="executor:self-report",
            outcome_status="VERIFIED_SUCCESS",
            evidence=evidence,
            parents=[],
        )
        return RunResult(receipt, {"payments": payments}, evidence)

    def false_done(self) -> RunResult:
        self.client.reset()
        now = datetime(2026, 1, 1, 13, tzinfo=timezone.utc)
        action = {
            "type": "order.update_delivery_address",
            "resource": "order:EXAMPLE-ORD-9",
            "parameters": {"address": "New address"},
        }
        status, _ = self.client.request(
            "POST",
            "/orders/EXAMPLE-ORD-9/address",
            {"address": "New address"},
            {"X-Simulate-Silent-Failure": "1"},
        )
        order = self.verifier.order("EXAMPLE-ORD-9")
        evidence = [
            {"agent_report": "DONE"},
            {"provider_http_status": status},
            {"authoritative_address": order["address"]},
        ]
        receipt = self._receipt(
            receipt_id="unsafe-remote-false-done",
            requested_action=action,
            authorized_action=action,
            executed_action=action,
            decision="ALLOW",
            authorization_time=now,
            execution_time=now + timedelta(seconds=1),
            verification_time=now + timedelta(seconds=2),
            external_state_reference="sandbox-http://orders/EXAMPLE-ORD-9",
            verification_source="executor:self-report",
            outcome_status="VERIFIED_SUCCESS",
            evidence=evidence,
        )
        return RunResult(receipt, {"order": order}, evidence)


class GuardedRemote(RemoteSystem):
    name = "guarded-remote"

    def expired_mandate(self) -> RunResult:
        self.client.reset()
        t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        auth_time = t0 + timedelta(minutes=5)
        exec_time = t0 + timedelta(minutes=11)
        action = {
            "type": "payment.create",
            "resource": "invoice:EXAMPLE-0001",
            "parameters": {"amount": 500, "currency": "EUR"},
        }
        payments = self.verifier.payments_for_invoice("EXAMPLE-0001")
        evidence = [
            {"mandate_not_after": _ts(t0 + timedelta(minutes=10))},
            {"execution_time": _ts(exec_time)},
            {"execution_time_validity": "expired"},
            {"verified_payment_count": len(payments)},
        ]
        receipt = self._receipt(
            receipt_id="guarded-remote-expired",
            requested_action=action,
            authorized_action=None,
            executed_action=None,
            decision="REAUTHORIZATION_REQUIRED",
            authorization_time=auth_time,
            execution_time=exec_time,
            verification_time=exec_time,
            external_state_reference="sandbox-http://payments/invoice/EXAMPLE-0001",
            verification_source="readonly-verifier:http",
            outcome_status="NOT_EXECUTED",
            evidence=evidence,
        )
        return RunResult(receipt, {"payments": payments}, evidence)

    def replay(self) -> RunResult:
        self.client.reset()
        now = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
        action = {
            "type": "payment.create",
            "resource": "invoice:EXAMPLE-0002",
            "parameters": {"amount": 120, "currency": "EUR", "idempotency_key": "K"},
        }
        self._create_payment("EXAMPLE-0002", 120, "K")
        payments = self.verifier.payments_for_invoice("EXAMPLE-0002")
        evidence = [
            {"deliveries": 2},
            {"replay_decision": "DENY"},
            {"verified_payment_count": len(payments)},
            {"provider_requests": len(self.verifier.audit())},
        ]
        receipt = self._receipt(
            receipt_id="guarded-remote-replay",
            requested_action=action,
            authorized_action=None,
            executed_action=None,
            decision="DENY",
            authorization_time=now + timedelta(seconds=1),
            execution_time=now + timedelta(seconds=1),
            verification_time=now + timedelta(seconds=2),
            external_state_reference="sandbox-http://payments/invoice/EXAMPLE-0002",
            verification_source="readonly-verifier:http",
            outcome_status="NOT_EXECUTED",
            evidence=evidence,
            parents=["receipt:original-payment-K"],
        )
        return RunResult(receipt, {"payments": payments}, evidence)

    def false_done(self) -> RunResult:
        self.client.reset()
        now = datetime(2026, 1, 1, 13, tzinfo=timezone.utc)
        action = {
            "type": "order.update_delivery_address",
            "resource": "order:EXAMPLE-ORD-9",
            "parameters": {"address": "New address"},
        }
        status, _ = self.client.request(
            "POST",
            "/orders/EXAMPLE-ORD-9/address",
            {"address": "New address"},
            {"X-Simulate-Silent-Failure": "1"},
        )
        order = self.verifier.order("EXAMPLE-ORD-9")
        evidence = [
            {"agent_report": "DONE"},
            {"provider_http_status": status},
            {"authoritative_address": order["address"]},
            {"verification": "mismatch"},
        ]
        receipt = self._receipt(
            receipt_id="guarded-remote-false-done",
            requested_action=action,
            authorized_action=action,
            executed_action=action,
            decision="ALLOW",
            authorization_time=now,
            execution_time=now + timedelta(seconds=1),
            verification_time=now + timedelta(seconds=2),
            external_state_reference="sandbox-http://orders/EXAMPLE-ORD-9",
            verification_source="readonly-verifier:http",
            outcome_status="FAILED",
            evidence=evidence,
        )
        return RunResult(receipt, {"order": order}, evidence)


def _wait_for_server(client: HttpClient) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            status, _ = client.request("GET", "/health")
            if status == 200:
                return
        except OSError:
            pass
        time.sleep(0.05)
    raise RuntimeError("authoritative sandbox did not become healthy")


def run_remote(system: RemoteSystem) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name in P0_SCENARIOS:
        rows.append(evaluate(name, load_scenario(name), getattr(system, name)()))
    return rows


def run_all() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="margelis-vdb-") as temp_dir:
        # stderr goes to a file so a chatty server can never fill a pipe and stall the run;
        # the port line is read with a deadline so a server that never starts fails fast.
        stderr_path = Path(temp_dir) / "server.err"
        stderr_file = open(stderr_path, "w", encoding="utf-8")
        proc = subprocess.Popen(
            [sys.executable, str(SERVER), "--db", str(Path(temp_dir) / "state.sqlite"), "--port", "0"],
            stdout=subprocess.PIPE,
            stderr=stderr_file,
            text=True,
        )
        try:
            if proc.stdout is None:
                raise RuntimeError("server stdout unavailable")
            import queue
            import threading
            lines: queue.Queue = queue.Queue()
            threading.Thread(target=lambda: lines.put(proc.stdout.readline()), daemon=True).start()
            try:
                port_line = lines.get(timeout=15).strip()
            except queue.Empty:
                port_line = ""
            if not port_line:
                stderr_file.flush()
                raise RuntimeError(f"sandbox failed to start: {stderr_path.read_text(encoding='utf-8')[-2000:]}")
            client = HttpClient(f"http://127.0.0.1:{int(port_line)}")
            _wait_for_server(client)
            verifier = ReadOnlyVerifier(client)
            unsafe = run_remote(UnsafeRemote(client, verifier))
            guarded = run_remote(GuardedRemote(client, verifier))
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3)
            stderr_file.close()

    return {
        "benchmark": "verified-delegation-v0.2-p0-process-sandbox",
        "scope": list(P0_SCENARIOS),
        "result_status": "PROCESS_SANDBOX_SELF_TEST_ONLY",
        "publication_warning": (
            "The authoritative state is a separate HTTP+SQLite process, but still a synthetic "
            "benchmark sandbox. This output is not a published third-party-system benchmark result."
        ),
        "systems": {"unsafe-remote": unsafe, "guarded-remote": guarded},
    }


def main() -> int:
    bundle = run_all()
    for system, rows in bundle["systems"].items():
        print(system)
        for row in rows:
            print(f"  {row['scenario']}: {'PASS' if row['pass'] else 'FAIL'}")
            for reason in row["reasons"]:
                print(f"    - {reason}")
    unsafe_all_fail = all(not row["pass"] for row in bundle["systems"]["unsafe-remote"])
    guarded_all_pass = all(row["pass"] for row in bundle["systems"]["guarded-remote"])
    return 0 if unsafe_all_fail and guarded_all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
