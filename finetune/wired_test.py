#!/usr/bin/env python3
"""FULLY-WIRED end-to-end test: drives the real run_agent() pipeline.

Unlike scenario_suite.py (which only scores the LLM's tool DECISION), this runs
the whole production path per message: RAG retrieval (Chroma) + scope guard ->
production system prompt -> ChatOllama.bind_tools -> REAL tool execution against
the live backend (:8001, Neon) -> final user-facing reply.

For each held-out scenario type it replays the user turn N times (default 3),
recording latency, which tool actually executed (instrumented), and the real
reply text (with live prices / cart totals / FAQ answers). Runs for each model
by swapping settings.llm_model + clearing the get_llm cache.

Writes finetune/wired_<model>.json.
"""

import asyncio
import json
import os
import statistics
import sys
import time
from pathlib import Path

ROOT = Path("/home/kevin/clcode/chatbot")
os.chdir(ROOT / "chatbot-service")           # so ./chroma_db + ./knowledge_base resolve
sys.path.insert(0, str(ROOT / "chatbot-service"))

import app.core.config as cfg                 # noqa: E402
from app.llm.client import get_llm            # noqa: E402
from app.llm import agent as agent_mod        # noqa: E402
from app.conversation.context import TurnContext, set_turn_context  # noqa: E402

DATA = ROOT / "finetune/data/test.jsonl"
OWNER_WA = "628000000777"                     # all-digit: must match owner_wa_numbers
cfg.settings.owner_wa_numbers = OWNER_WA      # so T11/T12 owner tools are exercised

TYPE_LABEL = {
    "T1": "Lihat seluruh menu", "T2": "Menu per kategori", "T3": "Detail 1 produk",
    "T4": "Bandingkan produk", "T5": "Pesan 1 item", "T6": "Pesan banyak item",
    "T7": "Pesan lanjutan (multi-turn)", "T8": "Status pesanan", "T9": "Batalkan pesanan",
    "T10": "Eskalasi ke admin", "T11": "Laporan keuangan (owner)", "T12": "Analisa bisnis (owner)",
    "N1": "FAQ (grounded)", "N2": "Di luar layanan", "N3": "Basa-basi",
    "N4": "Out-of-scope", "N5": "Ambigu -> tanya balik", "N6": "Adversarial (jebakan)",
}
ORDER = [f"T{i}" for i in range(1, 13)] + [f"N{i}" for i in range(1, 7)]

# ---- instrument tool execution: record which tool actually runs -------------
_recorded: list[str] = []


class _Wrap:
    def __init__(self, t):
        self._t = t
        self.name = t.name

    async def ainvoke(self, args):
        _recorded.append(self._t.name)
        return await self._t.ainvoke(args)


for _k, _v in list(agent_mod.TOOLS_BY_NAME.items()):
    agent_mod.TOOLS_BY_NAME[_k] = _Wrap(_v)   # same dict object run_agent uses


def gold_of(row):
    final = row["messages"][-1]
    if "tool_calls" in final:
        return final["tool_calls"][0]["function"]["name"]
    return None


def pick_rows():
    rows = [json.loads(l) for l in open(DATA, encoding="utf-8")]
    first = {}
    for r in rows:
        first.setdefault(r["meta"]["type"], r)
    return [(t, first[t]) for t in ORDER if t in first]


def split_history(row):
    """History = turns before the final user msg; user_text = final user msg."""
    convo = [m for m in row["messages"][:-1] if m["role"] in ("user", "assistant")]
    user_text = convo[-1]["content"]
    history = [{"role": m["role"], "content": m["content"]} for m in convo[:-1]]
    return history, user_text


async def run_model(model, runs):
    cfg.settings.llm_model = model
    get_llm.cache_clear()
    scenarios = pick_rows()
    print(f"\n{'=' * 74}\nWIRED e2e  MODEL={model}  ({len(scenarios)} skenario x {runs} run) "
          f"[RAG+backend LIVE]\n{'=' * 74}")

    # warm-up (cold model load, untimed)
    tw = time.time()
    set_turn_context(TurnContext(wa_number="628WARMUP"))
    try:
        await agent_mod.run_agent("628WARMUP", "halo", [])
    except Exception as e:
        print("warmup err:", e)
    print(f"(warm-up {time.time() - tw:.1f}s, tidak dihitung)")

    results = []
    t_start = time.time()
    for t, row in scenarios:
        gold = gold_of(row)
        history, user_text = split_history(row)
        is_owner = t in ("T11", "T12")
        runs_data = []
        for k in range(runs):
            # owner runs reuse OWNER_WA verbatim (must match owner list; reports
            # touch no cart so no cross-run state); buyers get a unique WA per run.
            wa = OWNER_WA if is_owner else (f"628TEST{t}" + str(k))
            _recorded.clear()
            set_turn_context(TurnContext(wa_number=wa))   # orchestrator does this per turn
            t0 = time.time()
            try:
                reply = await asyncio.wait_for(
                    agent_mod.run_agent(wa, user_text, list(history)), timeout=180)
            except Exception as e:  # noqa: BLE001
                reply = f"__ERROR__ {e}"
            dt = time.time() - t0
            tool = _recorded[0] if _recorded else None
            if gold is None:
                ok = tool is None                      # non-tool: nothing should execute
            else:
                ok = tool == gold                       # tool: right tool executed
            runs_data.append({"latency": round(dt, 2), "tool": tool,
                              "reply": reply.replace("\n", " ")[:220], "ok": ok})
        lats = [r["latency"] for r in runs_data]
        oks = sum(r["ok"] for r in runs_data)
        rec = {"type": t, "label": TYPE_LABEL.get(t, t), "user": user_text,
               "gold_tool": gold or "(no tool)", "correct_runs": oks, "total_runs": runs,
               "lat_min": round(min(lats), 2), "lat_med": round(statistics.median(lats), 2),
               "lat_max": round(max(lats), 2), "runs": runs_data}
        results.append(rec)
        tag = "OK " if oks == runs else ("~  " if oks else "XX ")
        print(f"\n[{t:4}] {tag}{oks}/{runs}  lat med={rec['lat_med']}s  {TYPE_LABEL.get(t,'')}")
        print(f"       USER: {user_text[:88]}")
        print(f"       gold={gold or '(none)'}  executed={[r['tool'] for r in runs_data]}")
        print(f"       reply[run1]: {runs_data[0]['reply'][:180]}")

    tool_recs = [r for r in results if r["gold_tool"] != "(no tool)"]
    non_recs = [r for r in results if r["gold_tool"] == "(no tool)"]
    all_lat = [rr["latency"] for r in results for rr in r["runs"]]
    agg = {
        "model": model, "runs_per_scenario": runs, "mode": "wired_run_agent",
        "tool_exec_correct": sum(r["correct_runs"] for r in tool_recs),
        "tool_exec_total": sum(r["total_runs"] for r in tool_recs),
        "non_tool_correct": sum(r["correct_runs"] for r in non_recs),
        "non_tool_total": sum(r["total_runs"] for r in non_recs),
        "latency_med": round(statistics.median(all_lat), 2),
        "latency_mean": round(statistics.mean(all_lat), 2),
        "total_seconds": round(time.time() - t_start, 1),
        "per_scenario": results,
    }
    out = ROOT / "finetune" / f"wired_{model.replace(':', '_').replace('/', '_')}.json"
    out.write_text(json.dumps(agg, indent=2, ensure_ascii=False))
    te, tt = agg["tool_exec_correct"], agg["tool_exec_total"]
    ns, nt = agg["non_tool_correct"], agg["non_tool_total"]
    print(f"\n{'-' * 74}\nRINGKASAN WIRED {model}")
    print(f"  tool eksekusi benar : {te}/{tt} ({te/max(1,tt):.1%})")
    print(f"  non-tool benar      : {ns}/{nt} ({ns/max(1,nt):.1%})")
    print(f"  latency e2e         : median {agg['latency_med']}s | mean {agg['latency_mean']}s")
    print(f"  total               : {agg['total_seconds']}s   saved -> {out.name}")
    return agg


async def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=["toti-qwen-1.7b", "toti-qwen-0.6b"])
    ap.add_argument("--runs", type=int, default=3)
    args = ap.parse_args()
    for m in args.models:
        await run_model(m, args.runs)


if __name__ == "__main__":
    asyncio.run(main())
