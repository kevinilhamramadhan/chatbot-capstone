"""Tools: financial_report / business_analytics — Owner-only, REAL data.

Both consume one backend endpoint: GET /reports/summary (X-Service-Key).
Until the backend ships it, get_report_summary returns None and the tools say
so honestly — no dummy numbers.
Access is gated on the sender's WA number being in OWNER_WA_NUMBERS.
"""

from datetime import datetime, timezone

from langchain_core.tools import tool

from app.backend_client import api as backend
from app.conversation.context import get_turn_context
from app.core.config import settings
from app.tools.formatting import rupiah

_DENIED = (
    "Maaf, laporan ini hanya untuk Owner Toti Cakery dan nomormu belum terdaftar "
    "sebagai Owner."
)
_UNAVAILABLE = (
    "Laporan belum bisa diambil — endpoint laporan di backend belum tersedia "
    "atau sedang gangguan. Coba lagi nanti ya."
)


def _is_owner(wa: str) -> bool:
    digits = "".join(c for c in wa if c.isdigit())
    owners = ["".join(c for c in o if c.isdigit()) for o in settings.owner_wa_list]
    return digits in owners


def _month_range() -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    return now.replace(day=1).strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d")


async def _summary() -> dict | None:
    start, end = _month_range()
    return await backend.get_report_summary(start, end)


@tool
async def financial_report() -> str:
    """Laporan keuangan bulan berjalan (khusus Owner): omzet, pengeluaran, laba.
    Gunakan hanya jika pelanggan adalah Owner dan meminta laporan keuangan.
    """
    if not _is_owner(get_turn_context().wa_number):
        return _DENIED
    data = await _summary()
    if data is None:
        return _UNAVAILABLE
    revenue = float(data.get("revenue") or 0)
    expenses = float(data.get("expenses") or 0)
    return (
        f"📊 *Laporan Keuangan* ({_month_range()[0]} s/d {_month_range()[1]})\n"
        f"Omzet (pembayaran masuk): {rupiah(revenue)}\n"
        f"Pengeluaran: {rupiah(expenses)}\n"
        f"Laba kotor: {rupiah(revenue - expenses)}\n"
        f"Jumlah pesanan: {data.get('order_count', '-')}"
    )


@tool
async def business_analytics() -> str:
    """Analitik bisnis bulan berjalan (khusus Owner): produk terlaris, rata-rata
    nilai pesanan. Gunakan hanya jika pelanggan adalah Owner.
    """
    if not _is_owner(get_turn_context().wa_number):
        return _DENIED
    data = await _summary()
    if data is None:
        return _UNAVAILABLE
    top = data.get("top_products") or []
    lines = [f"📈 *Analitik Bisnis* ({_month_range()[0]} s/d {_month_range()[1]})"]
    if top:
        lines.append("Produk terlaris:")
        for i, p in enumerate(top[:5], 1):
            lines.append(f"{i}) {p.get('nama_produk')} — {p.get('qty')} pcs"
                         f" ({rupiah(p.get('revenue', 0))})")
    else:
        lines.append("Belum ada penjualan di periode ini.")
    lines.append(f"Jumlah pesanan: {data.get('order_count', '-')}")
    lines.append(f"Rata-rata nilai pesanan: {rupiah(data.get('avg_order_value') or 0)}")
    return "\n".join(lines)
