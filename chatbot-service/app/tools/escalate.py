"""Tool: escalate_to_admin — human takeover (WA notify is REAL, storage is MOCK)."""

import logging

from langchain_core.tools import tool

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

    # 1) Set local takeover flag (+expiry). Backend storage is MOCK.
    expires = await store.activate_takeover(wa)

    # 2) Notify the admin via WhatsApp (REAL, via wwebjs-api) if configured.
    if settings.admin_wa_number:
        try:
            await whatsapp_client.send_text(
                settings.admin_wa_number,
                f"🔔 Permintaan butuh penanganan admin.\nDari: {wa}\nAlasan: {reason}",
            )
        except Exception as exc:  # noqa: BLE001 - notification best-effort
            logger.error("Failed to notify admin %s: %s", settings.admin_wa_number, exc)
    else:
        logger.warning("ADMIN_WA_NUMBER not set — cannot notify admin.")

    logger.info("Takeover active for %s until %s", wa, expires.isoformat())
    return (
        "Permintaanmu sudah aku teruskan ke admin kami ya. Mohon tunggu, admin akan "
        "menghubungimu langsung lewat chat ini. 🙏"
    )
