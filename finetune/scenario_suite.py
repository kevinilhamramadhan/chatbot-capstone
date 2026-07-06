#!/usr/bin/env python3
"""Timed, 3x-repeated behavioural scenario suite for the fine-tuned models.

For each held-out scenario TYPE (T1-T12 tool, N1-N6 non-tool) it picks a
representative row from the frozen test split and replays the user turn through
the SAME serving path as production (ChatOllama + bind_tools + production
sampling from config.py) N times (default 3), recording:

  - latency of every run (min / median / max)
  - the model's decision: tool call (name + args) or the cleaned text reply
  - correctness vs the gold label (right tool for tool rows; no tool for
    non-tool rows), and whether args exactly matched (tool rows)

Writes finetune/scenario_<model>.json and prints a readable per-scenario log.
This complements eval_tool_calling.py (which scores all 100 rows once for the
aggregate BFCL verdict) by showing behaviour + latency with repetition.
"""

import argparse
import json
import re
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "chatbot-service"))

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage  # noqa: E402
from langchain_ollama import ChatOllama  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.tools.registry import ALL_TOOLS  # noqa: E402

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)

# Human labels + expectation per type (for the report).
TYPE_LABEL = {
    "T1":  "Lihat seluruh menu            -> get_menu",
    "T2":  "Menu per kategori             -> get_menu(kategori)",
    "T3":  "Detail 1 produk               -> get_product_detail",
    "T4":  "Bandingkan produk             -> compare_products",
    "T5":  "Pesan 1 item                  -> add_to_cart",
    "T6":  "Pesan banyak item sekaligus   -> add_to_cart",
    "T7":  "Pesan lanjutan (multi-turn)   -> add_to_cart",
    "T8":  "Status pesanan                -> get_order_status",
    "T9":  "Batalkan pesanan              -> cancel_order",
    "T10": "Eskalasi ke admin             -> escalate_to_admin",
    "T11": "Laporan keuangan (owner)      -> financial_report",
    "T12": "Analisa bisnis (owner)        -> business_analytics",
    "N1":  "FAQ (grounded)                -> jawab teks, TANPA tool",
    "N2":  "Permintaan di luar layanan    -> teks, TANPA tool",
    "N3":  "Basa-basi / terima kasih      -> teks, TANPA tool",
    "N4":  "Out-of-scope                  -> tolak, TANPA tool",
    "N5":  "Ambigu                        -> tanya balik, TANPA tool",
    "N6":  "Adversarial (jebakan)         -> teks, TANPA tool",
}

ORDER = [f"T{i}" for i in range(1, 13)] + [f"N{i}" for i in range(1, 7)]


def to_lc_messages(messages):
    out = []
    for m in messages:
        if m["role"] == "system":
            out.append(SystemMessage(content=m["content"]))
        elif m["role"] == "user":
            out.append(HumanMessage(content=m["content"]))
        else:
            out.append(AIMessage(content=m.get("content") or ""))
    return out


def gold_of(row):
    final = row["messages"][-1]
    if "tool_calls" in final:
        fn = final["tool_calls"][0]["function"]
        return fn["name"], json.loads(fn["arguments"])
    return None, None


def canon(obj):
    if isinstance(obj, dict):
        return {k: canon(v) for k, v in sorted(obj.items())}
    if isinstance(obj, list):
        return [canon(v) for v in obj]
    return obj


def clean_text(t):
    return _THINK_RE.sub("", t or "").strip()


def pick_rows(data_path):
    rows = [json.loads(l) for l in open(data_path, encoding="utf-8")]
    first = {}
    for r in rows:
        t = r["meta"]["type"]
        first.setdefault(t, r)
    return [(t, first[t]) for t in ORDER if t in first]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--data", default=str(ROOT / "finetune/data/test.jsonl"))
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--num-ctx", type=int, default=8192)
    args = ap.parse_args()

    llm = ChatOllama(
        base_url=settings.ollama_base_url,
        model=args.model,
        temperature=settings.llm_temperature,   # production parity (0.7)
        top_p=settings.llm_top_p,                # production parity (0.8)
        num_ctx=args.num_ctx,
        num_predict=768,
    ).bind_tools(ALL_TOOLS)

    scenarios = pick_rows(args.data)
    print(f"\n{'=' * 72}\nMODEL: {args.model}   |   {len(scenarios)} skenario x {args.runs} run "
          f"(thinking ON, temp={settings.llm_temperature}/top_p={settings.llm_top_p})\n{'=' * 72}")

    # Warm-up: first call pays Ollama's cold model-load (~30-50s) — do it once,
    # untimed, so per-scenario latency reflects steady-state serving.
    tw = time.time()
    try:
        llm.invoke([HumanMessage(content="halo")])
    except Exception:
        pass
    print(f"(warm-up model load: {time.time() - tw:.1f}s — tidak dihitung)")

    results = []
    t_start = time.time()
    for t, row in scenarios:
        gname, gargs = gold_of(row)
        msgs = to_lc_messages(row["messages"][:-1])
        user_last = [m for m in row["messages"] if m["role"] == "user"][-1]["content"]
        runs = []
        for k in range(args.runs):
            t0 = time.time()
            try:
                resp = llm.invoke(msgs)
                dt = time.time() - t0
                calls = list(resp.tool_calls or [])
                if calls:
                    decided = f"TOOL {calls[0]['name']} {json.dumps(calls[0]['args'], ensure_ascii=False)}"
                    called_name = calls[0]["name"]
                    args_match = (canon(calls[0]["args"]) == canon(gargs)) if gname else None
                else:
                    decided = "TEXT: " + (clean_text(resp.content)[:160] or "(kosong)")
                    called_name = None
                    args_match = None
            except Exception as exc:  # noqa: BLE001
                dt = time.time() - t0
                decided, called_name, args_match = f"ERROR: {exc}", "__error__", None
            # correctness
            if gname is None:
                ok = called_name is None            # non-tool: must NOT call a tool
            else:
                ok = (called_name == gname)          # tool: must call the right tool
            runs.append({"latency": round(dt, 2), "decided": decided,
                         "ok": ok, "args_match": args_match})

        lats = [r["latency"] for r in runs]
        oks = sum(r["ok"] for r in runs)
        argm = sum(1 for r in runs if r["args_match"]) if gname else None
        rec = {
            "type": t, "label": TYPE_LABEL.get(t, t), "lang": row["meta"]["lang"],
            "user": user_last, "gold": (f"{gname} {json.dumps(gargs, ensure_ascii=False)}"
                                        if gname else "(no tool)"),
            "runs": runs,
            "lat_min": round(min(lats), 2), "lat_med": round(statistics.median(lats), 2),
            "lat_max": round(max(lats), 2),
            "correct_runs": oks, "total_runs": args.runs,
            "args_match_runs": argm,
        }
        results.append(rec)
        tag = "OK " if oks == args.runs else ("~  " if oks else "XX ")
        extra = f" args={argm}/{args.runs}" if (gname and oks) else ""
        print(f"\n[{t:4}] {tag}{oks}/{args.runs} correct{extra}  "
              f"lat med={rec['lat_med']}s ({rec['lat_min']}-{rec['lat_max']}s)  {TYPE_LABEL.get(t,'')}")
        print(f"       USER: {user_last[:90]}")
        print(f"       GOLD: {rec['gold'][:90]}")
        for i, r in enumerate(runs):
            print(f"       run{i+1} {r['latency']:>5}s  {r['decided'][:120]}")

    # aggregate
    tool_recs = [r for r in results if not r["gold"].startswith("(no tool)")]
    non_recs = [r for r in results if r["gold"].startswith("(no tool)")]
    all_lat = [rr["latency"] for r in results for rr in r["runs"]]
    agg = {
        "model": args.model,
        "runs_per_scenario": args.runs,
        "scenarios": len(results),
        "tool_selection_correct_runs": sum(r["correct_runs"] for r in tool_recs),
        "tool_selection_total_runs": sum(r["total_runs"] for r in tool_recs),
        "args_exact_runs": sum((r["args_match_runs"] or 0) for r in tool_recs),
        "non_tool_correct_runs": sum(r["correct_runs"] for r in non_recs),
        "non_tool_total_runs": sum(r["total_runs"] for r in non_recs),
        "latency_overall_med": round(statistics.median(all_lat), 2),
        "latency_overall_mean": round(statistics.mean(all_lat), 2),
        "total_seconds": round(time.time() - t_start, 1),
        "per_scenario": results,
    }
    out = ROOT / "finetune" / f"scenario_{args.model.replace(':', '_').replace('/', '_')}.json"
    out.write_text(json.dumps(agg, indent=2, ensure_ascii=False))

    ts, tt = agg["tool_selection_correct_runs"], agg["tool_selection_total_runs"]
    ns, nt = agg["non_tool_correct_runs"], agg["non_tool_total_runs"]
    print(f"\n{'-' * 72}\nRINGKASAN {args.model}")
    print(f"  tool-selection benar : {ts}/{tt} run  ({ts/max(1,tt):.1%})")
    print(f"  args exact-match     : {agg['args_exact_runs']}/{tt} run  ({agg['args_exact_runs']/max(1,tt):.1%})")
    print(f"  non-tool benar       : {ns}/{nt} run  ({ns/max(1,nt):.1%})")
    print(f"  latency (semua run)  : median {agg['latency_overall_med']}s | mean {agg['latency_overall_mean']}s")
    print(f"  total waktu          : {agg['total_seconds']}s")
    print(f"saved -> {out}")


if __name__ == "__main__":
    main()
