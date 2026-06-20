"""Live smoke test against the REAL qwen3 models via Ollama.

Backend product reads are mocked (so get_menu returns data without Nicholas's
backend), WhatsApp sends are stubbed. This exercises the full real path:
  real LLM tool-calling + real embeddings/RAG + scope guard + order flow.

Run from chatbot-service/ with the venv active and Ollama models pulled:
    python -m scripts.smoke_live
"""

import asyncio
import os
import tempfile

os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{tempfile.gettempdir()}/smoke.db")
os.environ.setdefault("CHROMA_PERSIST_DIR", f"{tempfile.gettempdir()}/smoke_chroma")

WA = "628123456789@c.us"

FAKE_PRODUCTS = [
    {"id": 5, "nama_produk": "Brownies Coklat", "deskripsi": "Brownies fudgy coklat premium",
     "kategori": "cake", "harga_jual": 50000, "image_url": "http://img/5.jpg", "is_active": True},
    {"id": 8, "nama_produk": "Bolu Pandan", "deskripsi": "Bolu lembut aroma pandan",
     "kategori": "cake", "harga_jual": 75000, "image_url": "http://img/8.jpg", "is_active": True},
    {"id": 9, "nama_produk": "Croissant Butter", "deskripsi": "Croissant renyah",
     "kategori": "pastry", "harga_jual": 25000, "image_url": "http://img/9.jpg", "is_active": True},
]


def _patch():
    from app.backend_client import products as products_api
    from app.payment.client import payment_client
    from app.whatsapp_client.client import whatsapp_client

    async def fake_list(only_active=True, kategori=None):
        return [p for p in FAKE_PRODUCTS if (not kategori or p["kategori"] == kategori)]

    async def fake_get(pid):
        return next((p for p in FAKE_PRODUCTS if p["id"] == pid), None)

    async def fake_send_text(wa, text):
        return {"ok": True}

    async def fake_send_image(wa, url, caption=None):
        return {"ok": True}

    async def fake_txn(order_id, amount, customer_name, customer_phone):
        return {"transaction_id": "MID-SMOKE", "order_id": order_id, "amount": amount,
                "bank": "bca", "va_number": "8808123456789012",
                "qr_url": f"http://qr/{order_id}.png", "status": "pending"}

    products_api.list_products = fake_list
    products_api.get_product = fake_get
    whatsapp_client.send_text = fake_send_text
    whatsapp_client.send_image = fake_send_image
    payment_client.create_transaction = fake_txn


async def main():
    _patch()
    from app.core.database import init_db
    from app.conversation.orchestrator import handle_message
    from knowledge_base import ingest

    print("→ Ingesting FAQ into ChromaDB (real embeddings)…")
    ingest.main()
    await init_db()

    turns = [
        "menu apa aja yang ada?",
        "jam buka toti cakery jam berapa?",
        "kamu bisa bantu kerjain PR matematika ku ga?",   # out of scope
        "aku mau pesan brownies coklat 2 sama bolu pandan 1",
    ]

    for t in turns:
        print(f"\n{'='*70}\nYOU: {t}")
        reply = await handle_message(WA, t)
        if reply.suppressed:
            print("BOT: [suppressed - takeover]")
        else:
            print("BOT:", (reply.text or "").strip())
            for m in reply.media:
                print("BOT[img]:", m.image_url, "|", m.caption)


if __name__ == "__main__":
    asyncio.run(main())
