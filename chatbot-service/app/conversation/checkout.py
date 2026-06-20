"""Checkout finalization: create order (MOCK backend) + payment (MOCK gateway).

Produces the QR + VA reply (PROMPT §10.8). The order record is tracked locally in
`pending_orders` so the background task can handle timeout + paid-detection.
"""

import json
import logging
from datetime import datetime, timedelta, timezone

from app.backend_client import mock_backend
from app.conversation import store
from app.conversation.states import State
from app.core.config import settings
from app.payment.client import payment_client
from app.tools.formatting import rupiah

logger = logging.getLogger(__name__)


def cart_total(cart: list[dict]) -> float:
    return sum(float(i["harga"]) * int(i["qty"]) for i in cart)


async def finalize_order(wa_number: str) -> str:
    cart = await store.get_cart(wa_number)
    cust = await store.get_customer(wa_number)
    if not cart:
        await store.set_state(wa_number, State.IDLE)
        return "Keranjangmu kosong. Mau lihat menu dulu?"

    total = cart_total(cart)
    payment_type = cust.get("payment_type", "full")
    if payment_type == "dp" and settings.allow_down_payment:
        amount_due = round(total * settings.down_payment_percentage)
    else:
        payment_type = "full"
        amount_due = total

    delivery = cust.get("metode_pengiriman", "pickup")

    # 1) Persist customer + order to backend — MOCK (endpoints not built yet).
    # Build the exact request shape the real POST /orders expects (see the Nicholas
    # doc): customer_id + items[{product_id, jumlah}]. `harga` is included only so
    # the mock can echo a realistic total; the real backend computes it from the DB.
    customer = await mock_backend.upsert_customer(
        wa_number, cust.get("nama", ""), cust.get("alamat", ""), cust.get("nomor_hp", "")
    )
    order_items = [
        {"product_id": c["product_id"], "jumlah": c["qty"], "harga": c["harga"]}
        for c in cart
    ]
    order = await mock_backend.create_order(
        customer_id=customer["customer_id"],
        items=order_items,
        metode_pengiriman=delivery,
        created_via="ChatBot",
    )
    order_ref = order["nomor_invoice"]

    # 2) Create the payment transaction via the (mock) gateway.
    try:
        txn = await payment_client.create_transaction(
            order_id=order_ref,
            amount=amount_due,
            customer_name=cust.get("nama", ""),
            customer_phone=cust.get("nomor_hp", ""),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Payment gateway error: %s", exc)
        return "Maaf, pembuatan tagihan gagal. Coba ulangi sebentar lagi ya 🙏"

    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.payment_timeout_minutes
    )

    # 3) Track locally for timeout + paid-detection.
    await store.create_pending_order(
        wa_number=wa_number,
        order_ref=order_ref,
        payment_ref=txn.get("transaction_id"),
        payment_type=payment_type,
        total_amount=total,
        amount_due=amount_due,
        items_json=json.dumps(cart, ensure_ascii=False),
        customer_json=json.dumps(cust, ensure_ascii=False),
        delivery_method=delivery,
        expires_at=expires_at,
    )

    # 4) Clear draft, move to awaiting payment.
    await store.set_cart(wa_number, [])
    await store.set_state(wa_number, State.AWAITING_PAYMENT)

    paid_label = "Pembayaran penuh" if payment_type == "full" else "DP 50%"
    return (
        f"Pesanan kamu sudah dibuat ✅\nNo. Invoice: *{order_ref}*\n\n"
        f"{paid_label} yang harus dibayar: *{rupiah(amount_due)}*"
        + (f" (total pesanan {rupiah(total)})" if payment_type == "dp" else "")
        + "\n\n"
        f"💳 Virtual Account {txn.get('bank', '').upper()}: *{txn.get('va_number')}*\n"
        f"Atau scan QRIS: {txn.get('qr_url')}\n\n"
        f"Batas waktu pembayaran: {settings.payment_timeout_minutes} menit. "
        "Pembayaran akan terdeteksi otomatis. Ketik *batal* kalau ingin membatalkan."
    )
