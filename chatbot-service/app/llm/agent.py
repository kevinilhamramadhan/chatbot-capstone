"""LLM agent: RAG retrieval + scope guard + tool calling.

Design note: tool outputs are returned to the user verbatim instead of being fed
back to the LLM for a second pass. With a small model (qwen3:1.7b) this keeps
real data (prices, order summaries) accurate and avoids hallucinated rephrasing.
"""

import json
import logging
import re

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.core.config import settings
from app.llm.client import get_llm
from app.llm.prompt import SYSTEM_PROMPT
from app.rag.store import retrieve
from app.tools.registry import ALL_TOOLS, TOOLS_BY_NAME

logger = logging.getLogger(__name__)

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)

OUT_OF_SCOPE_REPLY = (
    f"Maaf, aku hanya bisa membantu seputar {settings.store_name} ya — menu, pemesanan, "
    "pembayaran, pengiriman, dan info toko. Ada yang bisa kubantu soal itu? 😊"
)


def _clean(text: str | None) -> str:
    if not text:
        return ""
    return _THINK_RE.sub("", text).strip()


def _balanced_json_objects(text: str) -> list[str]:
    """Return top-level {...} substrings (handles nested braces)."""
    objs, depth, start = [], 0, None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth > 0:
            depth -= 1
            if depth == 0 and start is not None:
                objs.append(text[start : i + 1])
                start = None
    return objs


def _extract_text_tool_calls(content: str) -> list[dict]:
    """Fallback: with thinking OFF, qwen3 sometimes emits a tool call as plain
    JSON text (e.g. {"name": "get_menu", "arguments": {...}}) instead of a
    structured tool call. Recover those so they still execute.
    """
    calls: list[dict] = []
    for blob in _balanced_json_objects(content):
        try:
            d = json.loads(blob)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(d, dict):
            continue
        name = d.get("name")
        args = d.get("arguments", d.get("parameters", {}))
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except (json.JSONDecodeError, ValueError):
                args = {}
        if name in TOOLS_BY_NAME:
            calls.append({"name": name, "args": args if isinstance(args, dict) else {}})
    return calls


async def _run_tool_calls(calls: list[dict]) -> list[str]:
    outputs: list[str] = []
    for tc in calls:
        tool = TOOLS_BY_NAME.get(tc["name"])
        if tool is None:
            logger.warning("Requested unknown tool: %s", tc["name"])
            continue
        try:
            outputs.append(str(await tool.ainvoke(tc.get("args", {}))))
        except Exception as exc:  # noqa: BLE001
            logger.exception("Tool %s failed: %s", tc["name"], exc)
            outputs.append("Maaf, ada kendala saat memproses permintaanmu. Coba lagi ya 🙏")
    return outputs


async def run_agent(wa_number: str, user_text: str, history: list[dict]) -> str:
    # 1) Retrieval + scope guard (PROMPT §7).
    retrieval = retrieve(user_text)
    rag_context = retrieval.context_text() if retrieval.in_scope else None
    logger.info(
        "RAG best_sim=%.3f in_scope=%s", retrieval.best_similarity, retrieval.in_scope
    )

    # Keep the system message CONSTANT (system prompt + tool schemas) so Ollama
    # can reuse its cached prefix across turns — on CPU this turns a ~35s prefill
    # into ~5s. Variable RAG context goes into the user turn, not the system msg.
    messages: list = [SystemMessage(content=SYSTEM_PROMPT)]
    for h in history:
        messages.append(
            HumanMessage(content=h["content"])
            if h["role"] == "user"
            else AIMessage(content=h["content"])
        )
    if rag_context:
        user_content = (
            "Konteks FAQ (gunakan untuk menjawab kalau relevan):\n"
            f"{rag_context}\n\n---\nPesan pelanggan: {user_text}"
        )
    else:
        user_content = user_text
    messages.append(HumanMessage(content=user_content))

    llm = get_llm().bind_tools(ALL_TOOLS)

    try:
        ai: AIMessage = await llm.ainvoke(messages)
    except Exception as exc:  # noqa: BLE001
        logger.exception("LLM invocation failed: %s", exc)
        return "Maaf, lagi ada gangguan di sistem kami. Coba beberapa saat lagi ya 🙏"

    # 2) Collect tool calls — structured first, then text-JSON fallback (needed
    #    when qwen3 thinking is OFF and it emits the call as plain text).
    calls = [
        {"name": tc["name"], "args": tc.get("args", {})}
        for tc in (getattr(ai, "tool_calls", None) or [])
    ]
    if not calls:
        calls = _extract_text_tool_calls(_clean(ai.content))

    # 3) No tool call -> direct answer (FAQ / greeting / refusal).
    if not calls:
        answer = _clean(ai.content)
        # Hard scope guard: out-of-scope and no on-topic tool used -> refuse.
        if not rag_context and not answer:
            return OUT_OF_SCOPE_REPLY
        return answer or OUT_OF_SCOPE_REPLY

    # 4) Execute tools; their outputs are the user-facing reply.
    outputs = await _run_tool_calls(calls)
    if not outputs:
        return _clean(ai.content) or OUT_OF_SCOPE_REPLY
    return "\n\n".join(outputs)
