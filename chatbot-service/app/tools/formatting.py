"""Shared helpers for tools: currency formatting + product name resolution."""

from app.backend_client import products as products_api


def rupiah(value) -> str:
    try:
        return f"Rp{int(round(float(value))):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "harga belum tersedia"


def product_label(p: dict) -> str:
    return p.get("nama_produk") or p.get("nama") or f"Produk #{p.get('id')}"


async def resolve_product(query: str) -> dict | None:
    """Find a product by id or (fuzzy) name from the live backend list.

    Scores every candidate by token overlap and returns the BEST match, not the
    first partial hit. The old first-hit-wins loop returned the alphabetically
    first product sharing any word ("cake 22cm" -> "Cake 10cm", "giant cookies"
    -> "Bento Cookies"), silently putting the wrong item (and price) in the cart.
    Scoring by how much of the label the query covers makes the specific match
    ("Cake 22cm") beat the generic one ("Cake 10cm"). No shared token -> no match.
    """
    query = query.strip()
    if query.isdigit():
        p = await products_api.get_product(int(query))
        if p:
            return p
    items = await products_api.list_products(only_active=True)
    q = query.lower()
    q_tokens = set(q.split())
    if not q_tokens:
        return None

    best, best_score = None, 0.0
    for p in items:
        label = product_label(p).lower()
        if label == q:
            return p  # exact name always wins
        l_tokens = set(label.split())
        overlap = q_tokens & l_tokens
        if not overlap:
            continue
        # Absolute matched-token count dominates so a specific match wins over a
        # generic one (2 words of "Cake 22cm" beat the 1 word of a bare "Cake");
        # label+query coverage only breaks ties toward the tighter name. (An
        # earlier "+1 if substring" bonus let a 1-word label steal the match by
        # sharing its single word — this counts real overlap instead.)
        score = len(overlap) * 2 + len(overlap) / len(l_tokens) + len(overlap) / len(q_tokens)
        if score > best_score:
            best_score, best = score, p
    return best
