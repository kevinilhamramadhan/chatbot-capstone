"""Tool: escalate_to_admin — human takeover (backend C1 + WA notify, both real)."""

import logging

from langchain_core.tools import tool

from app.backend_client import api as backend
from app.conversation import store
from app.conversation.context import get_turn_context
from app.core.config import settings
from app.whatsapp_client.client import whatsapp_client

logger = logging.getLogger(__name__)


@tool
async def escalate_to_admin(reason: str) -> str:
    """Teruskan permintaan pelanggan ke admin manusia (human takeover).

    Gunakan untuk kue custom atau permintaan di luar kemampuan bot. `reason`
    berisi ringkasan singkat kebutuhan pelanggan.
    """
    wa = get_turn_context().wa_number

    # 1) Set takeover: local cache (fast per-message check) + backend (record).
    expires = await store.activate_takeover(wa)
    try:
        await backend.set_takeover(wa, True, expires.isoformat())
    except Exception as exc:  # noqa: BLE001 - local copy already set
        logger.warning("backend set_takeover failed: %s", exc)

    # 2) Notify admin(s): dynamic list from backend (C2), env fallback if empty.
    numbers = await backend.get_takeover_admin_numbers()
    if not numbers and settings.admin_wa_number:
        numbers = [settings.admin_wa_number]
    if not numbers:
        logger.warning("No admin number available (dynamic list empty & env unset).")
    for number in numbers:
        try:
            await whatsapp_client.send_text(
                number,
                f"🔔 Permintaan butuh penanganan admin.\nDari: {wa}\nAlasan: {reason}",
            )
        except Exception as exc:  # noqa: BLE001 - notification best-effort
            logger.error("Failed to notify admin %s: %s", number, exc)

    logger.info("Takeover active for %s until %s", wa, expires.isoformat())
    return (
        "Permintaanmu sudah aku teruskan ke admin kami ya. Mohon tunggu, admin akan "
        "menghubungimu langsung lewat chat ini. 🙏"
    )
