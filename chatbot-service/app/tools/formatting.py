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
    """Find a product by id or (fuzzy) name from the live backend list."""
    query = query.strip()
    if query.isdigit():
        p = await products_api.get_product(int(query))
        if p:
            return p
    items = await products_api.list_products(only_active=True)
    q = query.lower()
    # exact, then contains, then word overlap.
    for p in items:
        if product_label(p).lower() == q:
            return p
    for p in items:
        if q in product_label(p).lower():
            return p
    for p in items:
        if any(w in product_label(p).lower() for w in q.split()):
            return p
    return None
