from __future__ import annotations

import argparse
import json
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


def _json(handler: BaseHTTPRequestHandler, status: int, payload: object) -> None:
    raw = json.dumps(payload, sort_keys=True).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)


class StateStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._init()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    invoice TEXT NOT NULL,
                    amount INTEGER NOT NULL,
                    currency TEXT NOT NULL,
                    idempotency_key TEXT
                );
                CREATE TABLE IF NOT EXISTS orders (
                    id TEXT PRIMARY KEY,
                    address TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    method TEXT NOT NULL,
                    path TEXT NOT NULL,
                    body TEXT NOT NULL,
                    outcome TEXT NOT NULL
                );
                """
            )

    def reset(self) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM payments")
            db.execute("DELETE FROM requests")
            db.execute("DELETE FROM orders")
            db.execute("INSERT INTO orders(id, address) VALUES (?, ?)", ("EXAMPLE-ORD-9", "Old address"))

    def log(self, method: str, path: str, body: object, outcome: str) -> None:
        with self.connect() as db:
            db.execute(
                "INSERT INTO requests(method, path, body, outcome) VALUES (?, ?, ?, ?)",
                (method, path, json.dumps(body, sort_keys=True), outcome),
            )

    def create_payment(self, body: dict[str, object], idempotency_key: str | None) -> dict[str, object]:
        invoice = str(body["invoice"])
        amount = int(body["amount"])
        currency = str(body["currency"])
        with self.connect() as db:
            if idempotency_key:
                row = db.execute(
                    "SELECT * FROM payments WHERE idempotency_key = ? ORDER BY id LIMIT 1",
                    (idempotency_key,),
                ).fetchone()
                if row:
                    return {"created": False, "payment": dict(row), "idempotent_replay": True}
            cur = db.execute(
                "INSERT INTO payments(invoice, amount, currency, idempotency_key) VALUES (?, ?, ?, ?)",
                (invoice, amount, currency, idempotency_key),
            )
            row = db.execute("SELECT * FROM payments WHERE id = ?", (cur.lastrowid,)).fetchone()
            return {"created": True, "payment": dict(row), "idempotent_replay": False}

    def payments(self, invoice: str | None, key: str | None) -> list[dict[str, object]]:
        sql = "SELECT * FROM payments"
        args: list[object] = []
        where: list[str] = []
        if invoice:
            where.append("invoice = ?")
            args.append(invoice)
        if key:
            where.append("idempotency_key = ?")
            args.append(key)
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY id"
        with self.connect() as db:
            return [dict(row) for row in db.execute(sql, args).fetchall()]

    def update_order(self, order_id: str, address: str, silent_failure: bool) -> dict[str, object] | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
            if not row:
                return None
            if not silent_failure:
                db.execute("UPDATE orders SET address = ? WHERE id = ?", (address, order_id))
            row = db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
            return dict(row)

    def order(self, order_id: str) -> dict[str, object] | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
            return dict(row) if row else None

    def requests(self) -> list[dict[str, object]]:
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM requests ORDER BY id").fetchall()]


def make_handler(store: StateStore):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def _body(self) -> dict[str, object]:
            length = int(self.headers.get("Content-Length", "0"))
            return json.loads(self.rfile.read(length)) if length else {}

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            if parsed.path == "/health":
                _json(self, 200, {"status": "ok"})
                return
            if parsed.path == "/payments":
                rows = store.payments(query.get("invoice", [None])[0], query.get("idempotency_key", [None])[0])
                _json(self, 200, {"payments": rows})
                return
            if parsed.path.startswith("/orders/"):
                order_id = parsed.path.split("/", 2)[2]
                row = store.order(order_id)
                _json(self, 200 if row else 404, {"order": row})
                return
            if parsed.path == "/audit/requests":
                _json(self, 200, {"requests": store.requests()})
                return
            _json(self, 404, {"error": "not_found"})

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            body = self._body()
            if parsed.path == "/reset":
                store.reset()
                store.log("POST", parsed.path, body, "reset")
                _json(self, 200, {"reset": True})
                return
            if parsed.path == "/payments":
                try:
                    result = store.create_payment(body, self.headers.get("Idempotency-Key"))
                except (KeyError, TypeError, ValueError) as exc:
                    store.log("POST", parsed.path, body, f"invalid:{exc}")
                    _json(self, 400, {"error": "invalid_payment"})
                    return
                store.log("POST", parsed.path, body, "created" if result["created"] else "idempotent")
                _json(self, 201 if result["created"] else 200, result)
                return
            if parsed.path.startswith("/orders/") and parsed.path.endswith("/address"):
                order_id = parsed.path.split("/")[2]
                silent = self.headers.get("X-Simulate-Silent-Failure") == "1"
                row = store.update_order(order_id, str(body.get("address", "")), silent)
                store.log("POST", parsed.path, body, "silent_failure" if silent else "updated")
                _json(self, 200 if row else 404, {"accepted": True, "order_id": order_id})
                return
            _json(self, 404, {"error": "not_found"})

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    store = StateStore(Path(args.db))
    store.reset()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(store))
    print(server.server_address[1], flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
