"""Background worker: payment timeout + automatic paid-detection (PROMPT §10.9-10).

Runs on an interval (PAYMENT_CHECK_INTERVAL_SECONDS). For each pending order it:
- cancels + notifies if past PAYMENT_TIMEOUT_MINUTES,
- proactively notifies the customer once payment is detected as paid.

Also exposes notify_ready() for the "order is ready" proactive message (§10.13),
triggered via the internal endpoint since the backend status webhook is out of scope.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone

from app.backend_client import api as backend
from app.conversation import store
from app.conversation.states import State
from app.core.config import settings
from app.tools.formatting import rupiah
from app.whatsapp_client.client import whatsapp_client

logger = logging.getLogger(__name__)

_task: asyncio.Task | None = None


async def _notify(wa_number: str, text: str) -> None:
    try:
        await whatsapp_client.send_text(wa_number, text)
        await store.log_message(wa_number, "out", text, intent="proactive")
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to notify %s: %s", wa_number, exc)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


async def _check_once() -> None:
    pending = await store.list_orders_by_status("pending")
    now = datetime.now(timezone.utc)

    for order in pending:
        # 1) Timeout -> auto-cancel + notify.
        if now >= _aware(order.expires_at):
            await store.update_pending_order(order.id, status="expired")
            await store.set_state(order.wa_number, State.IDLE)
            await _notify(
                order.wa_number,
                f"Pesanan *{order.order_ref}* dibatalkan otomatis karena melewati "
                "batas waktu pembayaran. Silakan pesan lagi kapan saja ya 🙏",
            )
            continue

        # 2) Poll backend payment status (invoice: unpaid|partial|paid|refunded).
        try:
            res = await backend.get_payment_status(order.order_ref)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Payment status check failed for %s: %s", order.order_ref, exc)
            continue

        inv_status = (res or {}).get("invoice_status")
        if inv_status in ("paid", "partial") and not order.notified_paid:
            await store.update_pending_order(order.id, status="paid", notified_paid=True)
            await store.set_state(order.wa_number, State.ORDER_ACTIVE)
            await _notify(
                order.wa_number,
                "Pembayaran sudah kami terima ✅\n"
                f"Jumlah: {rupiah(order.amount_due)}. Pesananmu akan segera kami proses. "
                "Terima kasih! 🎂",
            )


async def notify_ready(order_id: int) -> bool:
    """Send the proactive 'order is ready' message (PROMPT §10.13)."""
    # order_id from the backend push = our pending_orders.order_ref (backend id).
    orders = await store.list_orders_by_status("paid", "ready")
    order = next((o for o in orders if o.order_ref == str(order_id)), None)
    if order is None:
        return False
    await store.update_pending_order(order.id, status="ready", notified_ready=True)

    msg = f"Kabar baik! Pesananmu *{order.order_ref}* sudah *siap* 🎉\n"
    if order.delivery_method == "delivery":
        msg += (
            "\nUntuk pengiriman, silakan pesan kurir (GoSend/GrabExpress) sendiri ke "
            "alamat toko berikut:\n"
            f"*{settings.store_name}*\n{settings.store_address}\n"
            "(salin alamat di atas ke aplikasi ojol ya)"
        )
    else:
        msg += f"\nSilakan diambil di {settings.store_name}, {settings.store_address}."
    await _notify(order.wa_number, msg)
    return True


async def _loop() -> None:
    interval = settings.payment_check_interval_seconds
    logger.info("Payment background worker started (interval=%ss)", interval)
    while True:
        try:
            await _check_once()
        except Exception as exc:  # noqa: BLE001
            logger.exception("Background check error: %s", exc)
        await asyncio.sleep(interval)


def start() -> None:
    global _task
    if _task is None or _task.done():
        _task = asyncio.create_task(_loop())


async def stop() -> None:
    global _task
    if _task and not _task.done():
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None
