"""Conversation states for the order flow (PROMPT §10)."""

from enum import StrEnum


class State(StrEnum):
    IDLE = "idle"                       # general Q&A / browsing; LLM + tools
    AWAITING_CART_CONFIRMATION = "awaiting_cart_confirmation"
    COLLECTING_IDENTITY = "collecting_identity"
    AWAITING_PAYMENT = "awaiting_payment"
    ORDER_ACTIVE = "order_active"       # paid, awaiting ready/pickup


# Simple affirmative/cancel keyword sets for deterministic steps.
CONFIRM_WORDS = {
    "sudah", "sudah sesuai", "sesuai", "betul", "benar", "ya", "yes", "ok", "oke",
    "lanjut", "lanjutkan", "fix", "gas", "iya", "setuju", "confirm",
}
CANCEL_WORDS = {
    "batal", "batalkan", "cancel", "gajadi", "gak jadi", "ga jadi", "tidak jadi",
    "stop",
}


def text_is_confirm(text: str) -> bool:
    t = text.strip().lower()
    return t in CONFIRM_WORDS or any(w in t for w in ("sudah sesuai", "lanjut bayar"))


def text_is_cancel(text: str) -> bool:
    t = text.strip().lower()
    return any(w in t for w in CANCEL_WORDS)
