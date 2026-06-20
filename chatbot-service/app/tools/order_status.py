"""Tool: get_order_status — reads the local pending order (backend GET is MOCK)."""

import json

from langchain_core.tools import tool

from app.conversation import store
from app.conversation.context import get_turn_context
from app.tools.formatting import rupiah

_STATUS_LABEL = {
    "pending": "Menunggu pembayaran",
    "paid": "Sudah dibayar, sedang diproses",
    "ready": "Siap diambil/dikirim",
    "expired": "Kedaluwarsa (belum dibayar)",
    "cancelled": "Dibatalkan",
}


@tool
async def get_order_status() -> str:
    """Cek status pesanan terakhir pelanggan. Gunakan saat pelanggan menanyakan
    progress atau status pesanannya.
    """
    # MOCK — backend GET /orders endpoint belum ada; status diambil dari DB lokal.
    wa = get_turn_context().wa_number
    order = await store.get_active_pending(wa)
    if order is None:
        return "Saat ini kamu belum punya pesanan yang sedang berjalan."

    items = json.loads(order.items_json or "[]")
    item_lines = "\n".join(f"• {it['nama']} x{it['qty']}" for it in items)
    label = _STATUS_LABEL.get(order.status, order.status)
    return (
        f"Status pesanan *{order.order_ref}*: {label}\n"
        f"{item_lines}\n"
        f"Total: {rupiah(order.total_amount)} (yang harus dibayar: {rupiah(order.amount_due)})"
    )
