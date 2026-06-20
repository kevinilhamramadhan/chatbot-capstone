"""Real product/FAQ reads against the backend (these endpoints exist).

Backend field names are Indonesian: nama_produk, harga_jual, deskripsi, kategori
(see Backend-Cakery/app/schemas/product.py).
"""

import logging

from app.backend_client.base import backend_client

logger = logging.getLogger(__name__)


async def list_products(only_active: bool = True, kategori: str | None = None) -> list[dict]:
    params: dict = {"only_active": str(only_active).lower()}
    if kategori:
        params["kategori"] = kategori
    # Clean path first, doubled path (current bug) as fallback.
    resp = await backend_client.get_first_ok(
        ["/products/", "/products/products/"], params=params
    )
    if resp is None:
        return []
    return resp.json()


async def get_product(product_id: int) -> dict | None:
    resp = await backend_client.get_first_ok(
        [f"/products/{product_id}", f"/products/products/{product_id}"]
    )
    if resp is None:
        return None
    return resp.json()


async def list_faq(only_active: bool = True) -> list[dict]:
    params = {"only_active": str(only_active).lower()}
    resp = await backend_client.get_first_ok(["/faq", "/faq/faq"], params=params)
    if resp is None:
        return []
    return resp.json()
