"""Tool: escalate_to_admin — human takeover (WA notify is REAL, storage is MOCK)."""

import logging

from langchain_core.tools import tool

from app.backend_client import mock_backend
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

    # 1) Set takeover flag (+expiry). Decision C1(b): backend is source of truth.
    # We keep a local copy for the fast per-message check and ALSO persist to the
    # backend (MOCK until POST /customers/{wa}/takeover exists — easy swap then).
    expires = await store.activate_takeover(wa)
    await mock_backend.set_takeover(wa, True, expires.isoformat())

    # 2) Notify the admin(s) via WhatsApp (REAL, via wwebjs-api).
    # Decision C2: which admin handles takeover is dynamic (Owner-configured via
    # RBAC). We fetch the handler numbers from the backend (MOCK for now) and fall
    # back to the ADMIN_WA_NUMBER env var until that endpoint exists.
    numbers = await mock_backend.get_takeover_admin_numbers()
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
