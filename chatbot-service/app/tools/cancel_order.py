"""Tool: cancel_order — cancels a still-unpaid order on the backend (B4)."""

import logging

from langchain_core.tools import tool

from app.backend_client import api as backend
from app.conversation import store
from app.conversation.context import get_turn_context
from app.conversation.states import State

logger = logging.getLogger(__name__)


@tool
async def cancel_order() -> str:
    """Batalkan pesanan pelanggan yang masih pending (belum dibayar).

    Gunakan saat pelanggan minta membatalkan pesanannya.
    """
    wa = get_turn_context().wa_number
    order = await store.get_active_pending(wa)

    if order is None:
        # Only a draft cart, not a finalized order.
        await store.set_cart(wa, [])
        await store.set_state(wa, State.IDLE)
        return "Oke, draft pesanan dikosongkan. Ada lagi yang bisa kubantu?"

    try:
        await backend.cancel_order(order.order_ref)  # order_ref = backend order id
    except Exception as exc:  # noqa: BLE001 - backend returns 409 if already paid
        logger.warning("cancel failed for %s: %s", order.order_ref, exc)
        return (
            "Pesanan ini sudah dibayar/diproses, jadi tidak bisa dibatalkan lewat chat. "
            "Silakan hubungi admin ya."
        )

    await store.update_pending_order(order.id, status="cancelled")
    await store.set_cart(wa, [])
    await store.set_state(wa, State.IDLE)
    return "Pesanan kamu sudah dibatalkan. Terima kasih 🙏"
