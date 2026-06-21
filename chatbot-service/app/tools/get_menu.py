"""Tool: get_menu — REAL, hits the backend product list."""

from langchain_core.tools import tool

from app.backend_client import products as products_api
from app.tools.formatting import product_label, rupiah


@tool
async def get_menu(kategori: str | None = None) -> str:
    """Ambil daftar menu/produk aktif Toti Cakery beserta harganya.

    Gunakan saat pelanggan menanyakan menu, daftar kue, atau harga secara umum.
    Parameter `kategori` opsional untuk memfilter (mis. 'cake', 'pastry').
    """
    items = await products_api.list_products(only_active=True, kategori=kategori)
    if not items:
        return "Maaf, daftar menu sedang tidak bisa diambil. Coba lagi sebentar lagi ya."

    lines = ["Berikut menu Toti Cakery:"]
    for p in items:
        # is_available is computed by the backend (recipe vs stock). Absent -> available.
        status = "" if p.get("is_available", True) else "  (sedang tidak tersedia)"
        lines.append(f"• {product_label(p)} — {rupiah(p.get('harga_jual'))}{status}")
    lines.append("\nMau lihat detail salah satu kue? Sebutkan namanya ya 😊")
    return "\n".join(lines)
