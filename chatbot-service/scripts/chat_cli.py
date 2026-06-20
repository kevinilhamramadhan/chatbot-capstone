"""Local end-to-end chat tester — no WhatsApp/phone needed.

Drives the real conversation brain (RAG + tools + order flow) straight through
`handle_message`, printing replies to the terminal. Outbound WhatsApp sends are
stubbed so you can test everything with just Ollama (+ optionally the backend)
running.

Usage (from chatbot-service/, with your venv active):
    python -m scripts.chat_cli                 # default test number
    python -m scripts.chat_cli 628111222333    # custom WA number

Commands inside the prompt:
    /quit                 exit
    /state                show current session state + cart
"""

import asyncio
import json
import sys

# Stub outbound WhatsApp so we don't need a live wwebjs session.
from app.whatsapp_client import client as wa_client


async def _fake_send_text(self, wa_number, text):  # noqa: ANN001
    print(f"\n  [WA→{wa_number}]\n  " + text.replace("\n", "\n  "))
    return {"ok": True}


async def _fake_send_image(self, wa_number, image_url, caption=None):  # noqa: ANN001
    print(f"\n  [WA IMG→{wa_number}] {image_url}  (caption: {caption})")
    return {"ok": True}


wa_client.WhatsAppClient.send_text = _fake_send_text
wa_client.WhatsAppClient.send_image = _fake_send_image

from app.conversation import store  # noqa: E402
from app.conversation.orchestrator import handle_message  # noqa: E402
from app.core.database import init_db  # noqa: E402


async def main() -> None:
    wa = sys.argv[1] if len(sys.argv) > 1 else "628000000001@c.us"
    await init_db()
    print(f"Chat as {wa}. Type a message (/quit to exit, /state to inspect).\n")

    loop = asyncio.get_event_loop()
    while True:
        try:
            text = await loop.run_in_executor(None, input, "you> ")
        except (EOFError, KeyboardInterrupt):
            break
        text = text.strip()
        if not text:
            continue
        if text == "/quit":
            break
        if text == "/state":
            s = await store.get_or_create_session(wa)
            print(f"  state={s.state}  cart={s.cart_json}  customer={s.customer_json}")
            order = await store.get_active_pending(wa)
            if order:
                print(f"  active order: {order.order_ref} status={order.status} due={order.amount_due}")
            continue

        reply = await handle_message(wa, text)
        if reply.suppressed:
            print("  [no reply — human takeover active]")
            continue
        if reply.text:
            print("bot> " + reply.text.replace("\n", "\n     "))
        for m in reply.media:
            print(f"     [image] {m.image_url} (caption: {m.caption})")

    print("\nbye.")


if __name__ == "__main__":
    asyncio.run(main())
