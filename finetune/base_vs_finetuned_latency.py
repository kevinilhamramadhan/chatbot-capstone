#!/usr/bin/env python3
"""Apples-to-apples reply-time: base qwen3:1.7b vs fine-tuned toti-qwen-1.7b.
Warm (model preloaded), backend real, production config (num_predict cap 768).
Measures run_agent() wall time per message, a few message types."""
import asyncio, os, sys, time, statistics
from pathlib import Path
ROOT = Path("/home/kevin/clcode/chatbot")
os.chdir(ROOT / "chatbot-service"); sys.path.insert(0, str(ROOT / "chatbot-service"))
import app.core.config as cfg
from app.llm.client import get_llm
from app.llm import agent as agent_mod
from app.conversation.context import TurnContext, set_turn_context

MSGS = [
    ("Tanya menu",        "apa aja yang dijual di sini kak?"),
    ("Pesan kue",         "pesan cake 15cm coklat 2 ya"),
    ("Status pesanan",    "pesananku udah jadi belum?"),
    ("FAQ (jam buka)",    "jam buka toko kapan kak?"),
    ("Sapaan",            "halo kak, selamat siang"),
]

async def bench(model, runs=3):
    cfg.settings.llm_model = model; cfg.settings.llm_num_predict = 768; get_llm.cache_clear()
    set_turn_context(TurnContext(wa_number="628BENCH"))
    await agent_mod.run_agent("628BENCH", "halo", [])  # warm-up, untimed
    out = {}
    for label, q in MSGS:
        ts = []
        for _ in range(runs):
            set_turn_context(TurnContext(wa_number="628BENCH"))
            t = time.time(); await agent_mod.run_agent("628BENCH", q, []); ts.append(time.time() - t)
        out[label] = round(statistics.median(ts), 1)
    return out

async def main():
    print("mengukur BASE qwen3:1.7b ...", flush=True)
    base = await bench("qwen3:1.7b")
    print("mengukur FINE-TUNED toti-qwen-1.7b ...", flush=True)
    ft = await bench("toti-qwen-1.7b")
    print(f"\n{'Pesan':20}{'BASE (dtk)':>12}{'FINE-TUNED (dtk)':>18}{'lebih cepat':>14}")
    for label, _ in MSGS:
        b, f = base[label], ft[label]
        print(f"{label:20}{b:>12}{f:>18}{f'{b/f:.1f}x':>14}")
    ab = statistics.mean(base.values()); af = statistics.mean(ft.values())
    print(f"{'RATA-RATA':20}{ab:>12.1f}{af:>18.1f}{f'{ab/af:.1f}x':>14}")
    print("BENCH_DONE")

asyncio.run(main())
