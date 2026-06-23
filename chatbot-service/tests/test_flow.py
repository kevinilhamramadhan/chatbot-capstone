"""End-to-end behaviour tests for the conversation flow (no Ollama needed).

The LLM and backend HTTP are mocked; everything else is the real code path. These
tests pin down the behaviour AND the data shapes the chatbot sends to the backend
(the contract handed to Nicholas), so they break loudly if that contract drifts.
"""

import json

import pytest

from app.backend_client import mock_backend
from app.conversation import background, store
from app.conversation.context import TurnContext, set_turn_context
from app.conversation.orchestrator import handle_message
from app.conversation.states import State

WA = "628123456789@c.us"

FAKE_PRODUCTS = [
    {"id": 5, "nama_produk": "Brownies Coklat", "deskripsi": "Brownies fudgy",
     "kategori": "cake", "harga_jual": 50000, "image_url": "http://img/5.jpg", "is_active": True},
    {"id": 8, "nama_produk": "Bolu Pandan", "deskripsi": "Bolu lembut",
     "kategori": "cake", "harga_jual": 75000, "image_url": None, "is_active": True},
]


@pytest.fixture(autouse=True)
def patch_externals(monkeypatch):
    """Mock backend product reads, the payment gateway, and WhatsApp sends."""
    from app.backend_client import products as products_api
    from app.payment.client import payment_client
    from app.whatsapp_client.client import whatsapp_client

    async def fake_list(only_active=True, kategori=None):
        return [p for p in FAKE_PRODUCTS if (not kategori or p["kategori"] == kategori)]

    async def fake_get(pid):
        return next((p for p in FAKE_PRODUCTS if p["id"] == pid), None)

    monkeypatch.setattr(products_api, "list_products", fake_list)
    monkeypatch.setattr(products_api, "get_product", fake_get)

    sent = []

    async def fake_send_text(wa, text):
        sent.append((wa, text))
        return {"ok": True}

    async def fake_create_txn(order_id, amount, customer_name, customer_phone):
        return {"transaction_id": "MID-TEST-1", "order_id": order_id, "amount": amount,
                "bank": "bca", "va_number": "8808123456789012",
                "qr_url": f"http://qr/{order_id}.png", "status": "pending"}

    monkeypatch.setattr(whatsapp_client, "send_text", fake_send_text)
    monkeypatch.setattr(payment_client, "create_transaction", fake_create_txn)
    return {"sent": sent}


async def _seed_cart_awaiting_confirmation(items):
    """Use the real add_to_cart tool to build the draft, like the LLM would."""
    from app.tools.add_to_cart import add_to_cart

    set_turn_context(TurnContext(wa_number=WA))
    out = await add_to_cart.ainvoke({"items": items})
    # add_to_cart asks the orchestrator to move to confirmation; do it.
    await store.set_state(WA, State.AWAITING_CART_CONFIRMATION)
    return out


# ── add_to_cart ───────────────────────────────────────────────────────────────
async def test_add_to_cart_resolves_price_and_merges():
    out = await _seed_cart_awaiting_confirmation(
        [{"product": "Brownies Coklat", "qty": 2}, {"product": "brownies", "qty": 1}]
    )
    cart = await store.get_cart(WA)
    assert len(cart) == 1                      # merged same product
    assert cart[0]["qty"] == 3
    assert cart[0]["harga"] == 50000
    assert "Rp150.000" in out                  # 3 * 50000


async def test_add_to_cart_unknown_product():
    set_turn_context(TurnContext(wa_number=WA))
    from app.tools.add_to_cart import add_to_cart
    out = await add_to_cart.ainvoke({"items": [{"product": "Pizza", "qty": 1}]})
    assert "tidak menemukan" in out.lower()
    assert await store.get_cart(WA) == []


async def test_add_to_cart_rejects_unavailable(monkeypatch):
    # Backend marks a product out of stock (C3 opsi b: is_available=False).
    from app.backend_client import products as products_api
    from app.tools.add_to_cart import add_to_cart

    habis = {"id": 99, "nama_produk": "Kue Habis", "harga_jual": 40000,
             "is_available": False, "is_active": True}

    async def fake_list(only_active=True, kategori=None):
        return [habis]

    async def fake_get(pid):
        return habis if pid == 99 else None

    monkeypatch.setattr(products_api, "list_products", fake_list)
    monkeypatch.setattr(products_api, "get_product", fake_get)

    set_turn_context(TurnContext(wa_number=WA))
    out = await add_to_cart.ainvoke({"items": [{"product": "Kue Habis", "qty": 1}]})
    assert "tidak tersedia" in out.lower()
    assert await store.get_cart(WA) == []


# ── Full happy path: confirm -> identity -> DP -> payment ─────────────────────
async def test_full_order_flow_with_dp():
    await _seed_cart_awaiting_confirmation([{"product": "Brownies Coklat", "qty": 2}])

    r = await handle_message(WA, "sudah sesuai")
    assert (await store.get_or_create_session(WA)).state == State.COLLECTING_IDENTITY
    assert "nama" in r.text.lower()

    await handle_message(WA, "Budi Santoso")
    await handle_message(WA, "Jl. Mawar No. 10, Batam")
    r = await handle_message(WA, "delivery")
    assert "nomor wa" in r.text.lower() or "nomor hp" in r.text.lower()

    r = await handle_message(WA, "ya")               # confirm autofill phone
    assert "penuh" in r.text.lower() or "dp" in r.text.lower()

    r = await handle_message(WA, "dp")               # choose DP 50%
    # Final reply must contain VA + the DP amount (50% of 100000 = 50000).
    assert "8808123456789012" in r.text
    assert "Rp50.000" in r.text

    session = await store.get_or_create_session(WA)
    assert session.state == State.AWAITING_PAYMENT
    assert json.loads(session.cart_json) == []       # cart cleared

    order = await store.get_active_pending(WA)
    assert order is not None
    assert order.payment_type == "dp"
    assert order.total_amount == 100000
    assert order.amount_due == 50000                 # DP 50%
    assert order.delivery_method == "delivery"
    assert order.status == "pending"
    cust = json.loads(order.customer_json)
    assert cust["nama"] == "Budi Santoso"
    assert cust["nomor_hp"] == "628123456789"        # autofilled from WA


async def test_full_payment_charges_full_amount():
    await _seed_cart_awaiting_confirmation([{"product": "Bolu Pandan", "qty": 2}])
    for msg in ("sudah sesuai", "Budi", "Jl. Test 1", "pickup", "ya", "full"):
        r = await handle_message(WA, msg)
    order = await store.get_active_pending(WA)
    assert order.payment_type == "full"
    assert order.amount_due == 150000                # 2 * 75000, full


async def test_identity_validation_rejects_bad_input():
    await _seed_cart_awaiting_confirmation([{"product": "Brownies Coklat", "qty": 1}])
    await handle_message(WA, "sudah sesuai")
    r = await handle_message(WA, "Budi")
    await handle_message(WA, "Jl. Test 1")
    await handle_message(WA, "delivery")
    r = await handle_message(WA, "12")               # invalid phone (too short)
    assert "valid" in r.text.lower()
    assert "nomor_hp" not in json.loads(
        (await store.get_or_create_session(WA)).customer_json
    )


# ── Cancellation during confirmation ──────────────────────────────────────────
async def test_cancel_during_confirmation():
    await _seed_cart_awaiting_confirmation([{"product": "Brownies Coklat", "qty": 1}])
    r = await handle_message(WA, "batal")
    assert (await store.get_or_create_session(WA)).state == State.IDLE
    assert await store.get_cart(WA) == []


# ── One active order per WA number ────────────────────────────────────────────
async def test_single_active_order_guard():
    from app.tools.add_to_cart import add_to_cart

    await store.create_pending_order(
        wa_number=WA, order_ref="INV-1", payment_type="full", total_amount=100,
        amount_due=100, items_json="[]", customer_json="{}", delivery_method="pickup",
        expires_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
    )
    set_turn_context(TurnContext(wa_number=WA))
    out = await add_to_cart.ainvoke({"items": [{"product": "Brownies Coklat", "qty": 1}]})
    assert "website" in out.lower()
    assert await store.get_cart(WA) == []


# ── get_order_status / cancel_order tools ─────────────────────────────────────
async def test_order_status_and_cancel_tools():
    from app.tools.cancel_order import cancel_order
    from app.tools.order_status import get_order_status

    await store.create_pending_order(
        wa_number=WA, order_ref="INV-9", payment_type="full", total_amount=100,
        amount_due=100, items_json=json.dumps([{"nama": "Brownies", "qty": 1}]),
        customer_json="{}", delivery_method="pickup",
        expires_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
    )
    set_turn_context(TurnContext(wa_number=WA))
    status = await get_order_status.ainvoke({})
    assert "INV-9" in status

    set_turn_context(TurnContext(wa_number=WA))
    out = await cancel_order.ainvoke({})
    assert "dibatalkan" in out.lower()
    assert await store.get_active_pending(WA) is None


# ── Human takeover suppresses auto-reply ──────────────────────────────────────
async def test_escalate_sets_takeover_and_suppresses(patch_externals):
    from app.tools.escalate import escalate_to_admin

    set_turn_context(TurnContext(wa_number=WA))
    await escalate_to_admin.ainvoke({"reason": "kue custom ulang tahun"})
    assert await store.is_takeover_active(WA) is True
    # Admin got notified.
    assert any("628999000111" == wa for wa, _ in patch_externals["sent"])
    # Next inbound message is suppressed (not auto-replied).
    reply = await handle_message(WA, "halo?")
    assert reply.suppressed is True


# ── Background worker: timeout + paid detection ───────────────────────────────
async def test_background_timeout_cancels(patch_externals):
    import datetime as dt
    past = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1)
    await store.create_pending_order(
        wa_number=WA, order_ref="INV-T", payment_type="full", total_amount=100,
        amount_due=100, items_json="[]", customer_json="{}", delivery_method="pickup",
        expires_at=past,
    )
    await background._check_once()
    order = await store.get_active_pending(WA)
    assert order is None                              # expired -> no longer active
    assert any("dibatalkan otomatis" in t for _, t in patch_externals["sent"])


async def test_background_detects_paid(monkeypatch, patch_externals):
    import datetime as dt
    from app.payment.client import payment_client

    future = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=30)
    await store.create_pending_order(
        wa_number=WA, order_ref="INV-P", payment_type="full", total_amount=100,
        amount_due=100, items_json="[]", customer_json="{}", delivery_method="pickup",
        expires_at=future,
    )

    async def fake_status(order_ref):
        return "paid"

    monkeypatch.setattr(payment_client, "get_status", fake_status)
    await background._check_once()

    order = await store.get_active_pending(WA)
    assert order.status == "paid"
    assert (await store.get_or_create_session(WA)).state == State.ORDER_ACTIVE
    assert any("sudah kami terima" in t for _, t in patch_externals["sent"])


# ── Contract guard: shape the chatbot sends to the backend (for Nicholas) ─────
async def test_create_order_mock_contract_shape():
    # Exact request shape the chatbot sends to the real POST /orders (Nicholas doc).
    order = await mock_backend.create_order(
        customer_id=1001,
        items=[{"product_id": 5, "jumlah": 2, "harga": 50000}],
        metode_pengiriman="pickup",
        created_via="ChatBot",
    )
    assert set(order) >= {"order_id", "nomor_invoice", "total_harga_pesanan",
                          "status", "invoice_status", "metode_pengiriman", "created_via"}
    assert order["created_via"] == "ChatBot"
    assert order["status"] == "pending"
    assert order["invoice_status"] == "unpaid"
    assert order["total_harga_pesanan"] == 100000
