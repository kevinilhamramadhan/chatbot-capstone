"""Deterministic intent router (runs before the LLM in IDLE state).

Why: with qwen3 thinking OFF (needed to stay under the 60s latency target), the
small model is unreliable at *deciding* to call data tools — it sometimes
hallucinates a menu/comparison instead of calling the tool. So for the critical,
hallucination-prone intents (menu, compare, order, product detail) we detect the
intent with keywords + live-catalog matching and call the tool directly. The LLM
(thinking off) only handles what's left: FAQ, greetings, and the scope guard —
which it does reliably and fast.

This matches the spec (§6): the state machine routes intents; tools serve
transactions; RAG serves general questions.
"""

import re

from app.backend_client import products as products_api
from app.tools.add_to_cart import add_to_cart
from app.tools.compare_products import compare_products
from app.tools.formatting import product_label
from app.tools.get_menu import get_menu
from app.tools.get_product_detail import get_product_detail

MENU_WORDS = ("menu", "daftar", "jual apa", "ada apa", "ada kue apa", "list",
              "produk apa", "katalog", "harga")
COMPARE_WORDS = ("beda", "bedanya", "banding", "bandingkan", "perbandingan",
                 " vs ", "dibanding")
ORDER_WORDS = ("pesan", "order", "beli", "mau ambil", "tambah pesanan", "checkout")
DETAIL_WORDS = ("detail", "lihat", "liat", "info", "lebih lanjut", "seperti apa")

_SPLIT_RE = re.compile(r"\s+sama\s+|\s+dan\s+|\s*[,+&]\s*")


def _name_words(p: dict) -> list[str]:
    return [w for w in product_label(p).lower().split() if len(w) >= 4]


def _score(p: dict, text: str) -> int:
    return sum(1 for w in _name_words(p) if w in text)


def _match_products(text: str, products: list[dict]) -> list[dict]:
    """Products whose name words appear in text, ordered by first appearance."""
    low = text.lower()
    hits = []
    for p in products:
        sc = _score(p, low)
        if sc:
            pos = min((low.find(w) for w in _name_words(p) if w in low), default=10**6)
            hits.append((pos, p))
    hits.sort(key=lambda x: x[0])
    return [p for _, p in hits]


def _extract_items(text: str, products: list[dict]) -> list[dict]:
    """Parse '<product> <qty>' pairs across segments (sama/dan/comma)."""
    items: list[dict] = []
    for seg in _SPLIT_RE.split(text):
        low = seg.lower()
        best, best_sc = None, 0
        for p in products:
            sc = _score(p, low)
            if sc > best_sc:
                best, best_sc = p, sc
        if not best:
            continue
        nums = re.findall(r"\d+", seg)
        qty = int(nums[0]) if nums else 1
        items.append({"product": product_label(best), "qty": qty})
    return items


def _has(text: str, words) -> bool:
    return any(w in text for w in words)


async def try_handle(text: str) -> str | None:
    """Return a reply if a data-tool intent is detected, else None (-> LLM).

    Assumes the caller already set the TurnContext (tools may queue media).
    """
    low = f" {text.lower().strip()} "
    products = await products_api.list_products(only_active=True)

    # 1) ORDER — needs an action word AND a recognizable product.
    if _has(low, ORDER_WORDS):
        items = _extract_items(text, products)
        if items:
            return str(await add_to_cart.ainvoke({"items": items}))
        # ambiguous order (e.g. custom cake) -> let the LLM handle/escalate.
        return None

    # 2) COMPARE — needs >=2 recognizable products.
    if _has(low, COMPARE_WORDS):
        names = [product_label(p) for p in _match_products(text, products)]
        if len(names) >= 2:
            return str(await compare_products.ainvoke({"products": names}))
        return "Mau membandingkan kue yang mana saja? Sebutkan minimal 2 ya 😊"

    # 3) MENU — generic listing.
    if _has(low, MENU_WORDS):
        return str(await get_menu.ainvoke({}))

    # 4) DETAIL — explicit detail word + a product, or message that is basically
    #    just a product name.
    matched = _match_products(text, products)
    if matched and (_has(low, DETAIL_WORDS) or len(text.split()) <= 4):
        return str(await get_product_detail.ainvoke({"product": product_label(matched[0])}))

    return None
