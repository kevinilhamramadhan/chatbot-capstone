"""Inbound webhook from wwebjs-api + internal control endpoints.

wwebjs-api posts events here (we configure BASE_WEBHOOK_URL to point at
/webhook/whatsapp). We only act on text `message` events; everything else is
acknowledged and ignored.
"""

import logging

from fastapi import APIRouter, BackgroundTasks, Request

from app.backend_client import mock_backend
from app.conversation import background
from app.conversation.orchestrator import handle_message
from app.conversation.store import deactivate_takeover
from app.whatsapp_client.client import whatsapp_client

logger = logging.getLogger(__name__)

router = APIRouter()


def _extract_message(payload: dict) -> tuple[str, str] | None:
    """Pull (sender_chat_id, text) from a wwebjs-api message event, or None."""
    if payload.get("dataType") != "message":
        return None
    data = payload.get("data") or {}
    msg = data.get("message") or data
    if msg.get("fromMe"):
        return None
    sender = msg.get("from") or ""
    if not sender or sender.endswith("@g.us"):  # ignore groups
        return None
    # Only plain text chats; media/stickers/etc. are skipped for now.
    if msg.get("type") not in (None, "chat", "text"):
        return None
    body = (msg.get("body") or "").strip()
    if not body:
        return None
    return sender, body


async def _process(sender: str, text: str) -> None:
    try:
        reply = await handle_message(sender, text)
        if reply.suppressed:
            return
        if reply.text:
            await whatsapp_client.send_text(sender, reply.text)
        for media in reply.media:
            await whatsapp_client.send_image(sender, media.image_url, media.caption)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error processing message from %s: %s", sender, exc)


@router.post("/whatsapp")
async def whatsapp_webhook(request: Request, bg: BackgroundTasks):
    payload = await request.json()
    extracted = _extract_message(payload)
    if extracted is None:
        return {"status": "ignored"}
    sender, text = extracted
    logger.info("WA in <- %s: %s", sender, text[:120])
    # Ack fast; do the LLM work in the background so wwebjs-api doesn't time out.
    bg.add_task(_process, sender, text)
    return {"status": "accepted"}


# ── Internal control endpoints (manual testing helpers) ───────────────────────
@router.post("/internal/takeover/{phone}/deactivate")
async def deactivate(phone: str):
    """Manually end a human-takeover session (PROMPT §12 — temporary)."""
    await deactivate_takeover(phone)
    await mock_backend.set_takeover(phone, False, None)  # keep backend in sync (MOCK)
    return {"status": "ok", "phone": phone, "human_takeover_active": False}


@router.post("/internal/orders/{order_id}/ready")
async def mark_ready(order_id: int):
    """Trigger the proactive 'order is ready' message (PROMPT §10.13).

    Stands in for the backend status webhook, which is out of scope here.
    """
    ok = await background.notify_ready(order_id)
    return {"status": "ok" if ok else "not_found", "order_id": order_id}
