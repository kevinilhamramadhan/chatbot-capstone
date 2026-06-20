"""MOCK backend client — endpoints below DO NOT EXIST on the real backend yet.

Every function here stands in for an endpoint Nicholas still has to build. They
return realistic dummy data so the conversation can be exercised end-to-end.
Each assumed contract is recorded in /MISSING_ENDPOINTS.md.

DO NOT pretend these are real. When the backend ships, swap these for real HTTP
calls in a sibling module and delete the mock.
"""

import logging
import random
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# In-memory stand-in for the future `customers` table.
_mock_customers: dict[str, dict] = {}


async def get_customer_by_wa(wa_number: str) -> dict | None:
    # MOCK — endpoint backend belum tersedia (GET /customers?nomor_wa=...)
    logger.info("[MOCK] get_customer_by_wa(%s)", wa_number)
    return _mock_customers.get(wa_number)


async def upsert_customer(wa_number: str, name: str, address: str, phone: str) -> dict:
    # MOCK — endpoint backend belum tersedia (POST /customers)
    logger.info("[MOCK] upsert_customer(%s)", wa_number)
    cust = {
        "customer_id": _mock_customers.get(wa_number, {}).get(
            "customer_id", random.randint(1000, 9999)
        ),
        "nomor_wa": wa_number,
        "nama": name,
        "alamat": address,
        "nomor_hp": phone,
    }
    _mock_customers[wa_number] = cust
    return cust


async def create_order(
    customer_id: int,
    items: list[dict],
    metode_pengiriman: str,
    created_via: str = "ChatBot",
) -> dict:
    """MOCK — endpoint backend belum tersedia (POST /orders).

    Request shape matches the real contract handed to Nicholas:
      { customer_id, items: [{product_id, jumlah}], metode_pengiriman, created_via }
    The real backend computes total from the DB; here `harga` may be included per
    item so the mock can echo a realistic total (real backend ignores it).
    """
    logger.info("[MOCK] create_order customer_id=%s, %d item(s)", customer_id, len(items))
    order_id = random.randint(10000, 99999)
    total = sum(float(i.get("harga", 0)) * int(i["jumlah"]) for i in items)
    # Field names mirror the C300 `orders`/`invoices` tables for an easy real swap.
    return {
        "order_id": order_id,
        "nomor_invoice": f"INV-{datetime.now(timezone.utc):%Y%m%d}-{order_id}",
        "total_harga_pesanan": total,
        "status": "pending",
        "invoice_status": "unpaid",
        "metode_pengiriman": metode_pengiriman,
        "created_via": created_via,
    }


async def get_order_status(order_ref: str) -> dict | None:
    # MOCK — endpoint backend belum tersedia (GET /orders/{ref})
    # The real status lives in the local pending_orders table for now; the
    # conversation layer reads that directly. This stub exists for interface
    # completeness.
    logger.info("[MOCK] get_order_status(%s)", order_ref)
    return None


async def set_takeover(wa_number: str, active: bool, expires_at: str | None) -> dict:
    # MOCK — endpoint backend belum tersedia (POST /customers/{wa}/takeover)
    logger.info("[MOCK] set_takeover(%s, active=%s)", wa_number, active)
    return {"nomor_wa": wa_number, "human_takeover_active": active, "expires_at": expires_at}
