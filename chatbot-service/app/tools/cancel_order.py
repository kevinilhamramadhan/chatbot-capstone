"""Tool: cancel_order — cancels a still-unpaid order (backend update is MOCK)."""

from langchain_core.tools import tool

from app.conversation import store
from app.conversation.context import get_turn_context
from app.conversation.states import State


@tool
async def cancel_order() -> str:
    """Batalkan pesanan pelanggan yang masih pending (belum dibayar).

    Gunakan saat pelanggan minta membatalkan pesanannya.
    """
    # MOCK — backend cancel endpoint belum ada; status dikelola di DB lokal.
    wa = get_turn_context().wa_number
    order = await store.get_active_pending(wa)

    if order is None:
        # Maybe they only have a draft cart, not a finalized order.
        await store.set_cart(wa, [])
        await store.set_state(wa, State.IDLE)
        return "Oke, draft pesanan dikosongkan. Ada lagi yang bisa kubantu?"

    if order.status != "pending":
        return (
            "Pesanan ini sudah dibayar/diproses, jadi tidak bisa dibatalkan lewat chat. "
            "Silakan hubungi admin ya."
        )

    await store.update_pending_order(order.id, status="cancelled")
    await store.set_cart(wa, [])
    await store.set_state(wa, State.IDLE)
    return f"Pesanan *{order.order_ref}* sudah dibatalkan. Terima kasih 🙏"
