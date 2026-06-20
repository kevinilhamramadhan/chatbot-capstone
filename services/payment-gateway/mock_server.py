"""MOCK Midtrans payment gateway — standalone FastAPI service.

This is a placeholder. It generates realistic-looking VA numbers / QR strings and
lets you flip a transaction to "paid" for manual testing. It does NOT talk to
Midtrans and contains no real credentials (PROMPT §11).

Run standalone:  uvicorn mock_server:app --port 9000
"""

import os
import random
import string
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="MOCK Midtrans Payment Gateway", version="0.1.0")

# Optional: auto-mark paid after N seconds (0 = never, rely on debug endpoint).
AUTO_PAY_SECONDS = int(os.getenv("MOCK_AUTO_PAY_SECONDS", "0"))
EXPIRY_MINUTES = int(os.getenv("MOCK_EXPIRY_MINUTES", "30"))
BANKS = ["bca", "bni", "bri", "mandiri"]

# In-memory transaction store: order_id -> record
_txns: dict[str, dict] = {}


class CreateTxnRequest(BaseModel):
    order_id: str
    amount: float
    customer_name: str
    customer_phone: str


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _resolve_status(rec: dict) -> str:
    """Lazily compute status from timers (expiry / optional auto-pay)."""
    if rec["status"] in ("paid", "failed"):
        return rec["status"]
    now = _now()
    if AUTO_PAY_SECONDS and (now - rec["created_at"]).total_seconds() >= AUTO_PAY_SECONDS:
        rec["status"] = "paid"
    elif now >= rec["expiry_at"]:
        rec["status"] = "expired"
    return rec["status"]


@app.post("/transactions")
def create_transaction(req: CreateTxnRequest):
    txn_id = "MOCK-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=10))
    bank = random.choice(BANKS)
    va_number = "".join(random.choices(string.digits, k=12))
    expiry_at = _now() + timedelta(minutes=EXPIRY_MINUTES)
    rec = {
        "transaction_id": txn_id,
        "order_id": req.order_id,
        "qr_url": f"https://mock-midtrans.local/qr/{txn_id}.png",
        "va_number": va_number,
        "bank": bank,
        "amount": req.amount,
        "expiry_time": expiry_at.isoformat(),
        "expiry_at": expiry_at,
        "created_at": _now(),
        "status": "pending",
    }
    _txns[req.order_id] = rec
    return _public(rec)


@app.get("/transactions/{order_id}")
def get_status(order_id: str):
    rec = _txns.get(order_id)
    if not rec:
        raise HTTPException(404, "unknown order_id")
    return {"order_id": order_id, "status": _resolve_status(rec)}


@app.post("/debug/mark-paid/{order_id}")
def debug_mark_paid(order_id: str):
    """Manual test helper: force a transaction to paid."""
    rec = _txns.get(order_id)
    if not rec:
        raise HTTPException(404, "unknown order_id")
    rec["status"] = "paid"
    return {"order_id": order_id, "status": "paid"}


@app.get("/health")
def health():
    return {"status": "ok", "transactions": len(_txns)}


def _public(rec: dict) -> dict:
    return {
        k: rec[k]
        for k in (
            "transaction_id",
            "order_id",
            "qr_url",
            "va_number",
            "bank",
            "amount",
            "expiry_time",
            "status",
        )
    }
