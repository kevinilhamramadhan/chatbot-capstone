"""Tools: financial_report / business_analytics — Owner-only, MOCK data.

Lowest priority (PROMPT §9). Returns formatted text only; no UI, no dashboard.
Access is gated on the sender's WA number being in OWNER_WA_NUMBERS.
"""

from langchain_core.tools import tool

from app.conversation.context import get_turn_context
from app.core.config import settings
from app.tools.formatting import rupiah

_DENIED = (
    "Maaf, laporan ini hanya untuk Owner Toti Cakery dan nomormu belum terdaftar "
    "sebagai Owner."
)


def _is_owner(wa: str) -> bool:
    digits = "".join(c for c in wa if c.isdigit())
    owners = ["".join(c for c in o if c.isdigit()) for o in settings.owner_wa_list]
    return digits in owners


@tool
async def financial_report() -> str:
    """Laporan keuangan ringkas (khusus Owner). Gunakan hanya jika pelanggan
    adalah Owner dan meminta laporan keuangan.
    """
    # MOCK — endpoint laporan keuangan backend belum ada.
    wa = get_turn_context().wa_number
    if not _is_owner(wa):
        return _DENIED
    return (
        "📊 *Laporan Keuangan (DATA DUMMY)*\n"
        f"Pendapatan bulan ini: {rupiah(12_500_000)}\n"
        f"Pengeluaran: {rupiah(7_300_000)}\n"
        f"Laba kotor: {rupiah(5_200_000)}\n"
        "_Catatan: ini data contoh; endpoint backend belum tersedia._"
    )


@tool
async def business_analytics() -> str:
    """Analitik bisnis ringkas (khusus Owner): produk terlaris, dll.
    Gunakan hanya jika pelanggan adalah Owner.
    """
    # MOCK — endpoint analitik backend belum ada.
    wa = get_turn_context().wa_number
    if not _is_owner(wa):
        return _DENIED
    return (
        "📈 *Analitik Bisnis (DATA DUMMY)*\n"
        "Produk terlaris: 1) Brownies Coklat  2) Bolu Pandan  3) Croissant\n"
        "Rata-rata nilai pesanan: " + rupiah(185_000) + "\n"
        "_Catatan: ini data contoh; endpoint backend belum tersedia._"
    )
