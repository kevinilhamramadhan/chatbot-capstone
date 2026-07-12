#!/usr/bin/env python3
"""Measure real end-to-end reply time for a 'tanya menu' message through the FULL
wired chatbot (run_agent: RAG + backend get_menu + reply), to explain the
70s-before vs <5s-now gap. Tests base qwen3:1.7b (capped + uncapped) vs the
fine-tuned toti-qwen-1.7b.
"""
import asyncio, os, sys, time
from pathlib import Path
ROOT = Path("/home/kevin/clcode/chatbot")
os.chdir(ROOT / "chatbot-service")
sys.path.insert(0, str(ROOT / "chatbot-service"))

import app.core.config as cfg
from app.llm.client import get_llm
from app.llm import agent as agent_mod
from app.conversation.context import TurnContext, set_turn_context

_rec = []
class _W:
    def __init__(s, t): s._t = t; s.name = t.name
    async def ainvoke(s, a): _rec.append(s._t.name); return await s._t.ainvoke(a)
for k, v in list(agent_mod.TOOLS_BY_NAME.items()):
    agent_mod.TOOLS_BY_NAME[k] = _W(v)

Q = "apa aja yang dijual di sini kak?"

async def run(model, num_predict, runs=3, label=""):
    cfg.settings.llm_model = model
    cfg.settings.llm_num_predict = num_predict
    get_llm.cache_clear()
    set_turn_context(TurnContext(wa_number="628MENU"))
    # warmup (untimed)
    await agent_mod.run_agent("628MENU", "halo", [])
    times, tools, ntok = [], [], []
    for i in range(runs):
        _rec.clear()
        set_turn_context(TurnContext(wa_number="628MENU"))
        t0 = time.time()
        reply = await agent_mod.run_agent("628MENU", Q, [])
        dt = time.time() - t0
        times.append(dt); tools.append(_rec[0] if _rec else None)
        ntok.append(len(reply))
    cap = "uncapped" if num_predict in (-1, None) else f"cap {num_predict}"
    print(f"\n[{label}]  {model}  ({cap})")
    print(f"   waktu per jawaban: {[round(t,1) for t in times]} dtk   median {sorted(times)[len(times)//2]:.1f} dtk")
    print(f"   tool tereksekusi : {tools}")
    print(f"   panjang balasan  : {ntok} char")

async def main():
    # 1) base qwen3:1.7b with the NEW cap (current production config)
    await run("qwen3:1.7b", 768, 3, "BASE capped")
    # 2) fine-tuned toti-qwen-1.7b with the cap (what I showed earlier)
    await run("toti-qwen-1.7b", 768, 3, "FINE-TUNED capped")
    # 3) base qwen3:1.7b UNCAPPED — reproduces the old ~70s runaway
    await run("qwen3:1.7b", -1, 2, "BASE UNCAPPED (config lama)")

asyncio.run(main())
print("\nMENU_LATENCY_DONE")
