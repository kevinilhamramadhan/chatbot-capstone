"""Dependency-light unit tests (no Ollama / backend / DB needed)."""

from app.conversation.states import text_is_cancel, text_is_confirm
from app.rag.store import RetrievalResult
from app.tools.add_to_cart import cart_summary
from app.tools.formatting import rupiah


def test_rupiah_formats_thousands():
    assert rupiah(150000) == "Rp150.000"
    assert rupiah(1500) == "Rp1.500"
    assert rupiah(None) == "harga belum tersedia"


def test_confirm_and_cancel_keywords():
    assert text_is_confirm("sudah sesuai")
    assert text_is_confirm("ya")
    assert text_is_cancel("batalkan")
    assert text_is_cancel("ga jadi")
    assert not text_is_confirm("mau nambah lagi")
    assert not text_is_cancel("lanjut")


def test_cart_summary_totals():
    cart = [
        {"nama": "Brownies", "harga": 50000, "qty": 2},
        {"nama": "Bolu", "harga": 75000, "qty": 1},
    ]
    out = cart_summary(cart)
    assert "Brownies x2" in out
    assert "Rp175.000" in out  # 2*50000 + 75000


def test_scope_guard_threshold():
    in_scope = RetrievalResult(["doc"], [{}], [0.8])
    out_scope = RetrievalResult(["doc"], [{}], [0.1])
    assert in_scope.in_scope is True
    assert out_scope.in_scope is False
    assert RetrievalResult([], [], []).best_similarity == 0.0
