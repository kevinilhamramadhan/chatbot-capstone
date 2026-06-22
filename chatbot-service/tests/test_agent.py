"""Agent wiring tests: tool-call execution + scope guard (LLM mocked, no Ollama)."""

import pytest
from langchain_core.messages import AIMessage

from app.conversation.context import TurnContext, set_turn_context
from app.llm import agent as agent_mod
from app.rag.store import RetrievalResult

WA = "628123456789@c.us"

FAKE_PRODUCTS = [
    {"id": 5, "nama_produk": "Brownies Coklat", "harga_jual": 50000, "is_active": True},
]


class _FakeBound:
    def __init__(self, ai):
        self._ai = ai

    async def ainvoke(self, messages):
        return self._ai


class _FakeLLM:
    def __init__(self, ai):
        self._ai = ai

    def bind_tools(self, tools):
        return _FakeBound(self._ai)


def _mock_llm(monkeypatch, ai_message):
    monkeypatch.setattr(agent_mod, "get_llm", lambda: _FakeLLM(ai_message))


def _mock_retrieval(monkeypatch, similarity):
    def fake_retrieve(query, top_k=None):
        return RetrievalResult(
            documents=["Q: jam buka? A: 09-19"] if similarity > 0 else [],
            metadatas=[{}],
            similarities=[similarity] if similarity > 0 else [],
        )
    monkeypatch.setattr(agent_mod, "retrieve", fake_retrieve)


async def test_agent_executes_tool_call(monkeypatch):
    from app.backend_client import products as products_api

    async def fake_list(only_active=True, kategori=None):
        return FAKE_PRODUCTS
    monkeypatch.setattr(products_api, "list_products", fake_list)

    _mock_retrieval(monkeypatch, 0.0)
    ai = AIMessage(content="", tool_calls=[
        {"name": "get_menu", "args": {}, "id": "1", "type": "tool_call"}
    ])
    _mock_llm(monkeypatch, ai)

    set_turn_context(TurnContext(wa_number=WA))
    out = await agent_mod.run_agent(WA, "menu apa aja", history=[])
    assert "Brownies Coklat" in out          # real tool output reached the user
    assert "Rp50.000" in out


async def test_agent_text_json_tool_call_fallback(monkeypatch):
    """Thinking OFF: qwen3 may emit the tool call as plain JSON text instead of a
    structured tool_call. The agent must still detect and execute it."""
    from app.backend_client import products as products_api

    async def fake_list(only_active=True, kategori=None):
        return FAKE_PRODUCTS
    monkeypatch.setattr(products_api, "list_products", fake_list)

    _mock_retrieval(monkeypatch, 0.0)
    # No structured tool_calls; tool call sits in content as text.
    ai = AIMessage(content='{"name": "get_menu", "arguments": {}}')
    _mock_llm(monkeypatch, ai)

    set_turn_context(TurnContext(wa_number=WA))
    out = await agent_mod.run_agent(WA, "menu apa aja", history=[])
    assert "Brownies Coklat" in out          # executed, not echoed as JSON
    assert "{" not in out                     # raw JSON not leaked to user


async def test_agent_answers_from_faq_when_in_scope(monkeypatch):
    _mock_retrieval(monkeypatch, 0.9)        # high similarity -> in scope
    ai = AIMessage(content="Kami buka jam 09.00-19.00 WIB.")
    _mock_llm(monkeypatch, ai)

    set_turn_context(TurnContext(wa_number=WA))
    out = await agent_mod.run_agent(WA, "jam buka?", history=[])
    assert "09.00" in out


async def test_agent_scope_guard_refuses_out_of_topic(monkeypatch):
    _mock_retrieval(monkeypatch, 0.05)       # below threshold -> out of scope
    ai = AIMessage(content="")               # model produced nothing usable
    _mock_llm(monkeypatch, ai)

    set_turn_context(TurnContext(wa_number=WA))
    out = await agent_mod.run_agent(WA, "siapa presiden?", history=[])
    assert out == agent_mod.OUT_OF_SCOPE_REPLY


async def test_agent_strips_think_tags(monkeypatch):
    _mock_retrieval(monkeypatch, 0.0)
    ai = AIMessage(content="<think>reasoning here</think>Halo! Ada yang bisa dibantu?")
    _mock_llm(monkeypatch, ai)

    set_turn_context(TurnContext(wa_number=WA))
    out = await agent_mod.run_agent(WA, "halo", history=[])
    assert "reasoning here" not in out
    assert "Halo!" in out
