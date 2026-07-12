#!/usr/bin/env python3
"""Bandingkan 3 model embedding untuk RAG FAQ Toti Cakery: akurasi retrieval +
kecepatan. Embed 5 dokumen FAQ + query uji, ranking cosine (persis yang Chroma
lakukan). Tanpa Chroma/config coupling — murni kualitas embedding."""
import sys, time, math, glob
from pathlib import Path
sys.path.insert(0, "/home/kevin/clcode/chatbot/chatbot-service")
from langchain_ollama import OllamaEmbeddings

FAQ_DIR = Path("/home/kevin/clcode/chatbot/chatbot-service/knowledge_base/faq")
DOCS = [open(f, encoding="utf-8").read() for f in sorted(glob.glob(str(FAQ_DIR / "*.txt")))]
# faq1 jam buka | faq2 custom | faq3 pengiriman | faq4 pembayaran | faq5 halal/tahan

# (query, index dokumen yang benar).  None = out-of-scope (harus TIDAK cocok kuat)
QUERIES = [
    ("jam buka toko kapan kak?", 0), ("toti cakery buka jam berapa sih?", 0),
    ("bisa pesan kue ulang tahun desain khusus?", 1), ("bisa bikin kue custom ga?", 1),
    ("cara pengirimannya gimana?", 2), ("kuenya bisa dikirim ga ke rumah?", 2),
    ("bayarnya pakai apa aja?", 3), ("bisa transfer bank atau qris?", 3),
    ("kue di sini halal ga?", 4), ("kue tahan berapa lama kalau disimpan?", 4),
    ("resep rendang yang enak dong", None), ("harga iphone terbaru berapa?", None),
    ("cuaca hari ini gimana ya?", None), ("rekomendasi film bagus apa?", None),
]
MODELS = ["qwen3-embedding:0.6b", "nomic-embed-text", "all-minilm"]


def norm(v):
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def cos(a, b):
    return sum(x * y for x, y in zip(a, b))


def run(model):
    emb = OllamaEmbeddings(base_url="http://localhost:11434", model=model)
    doc_vecs = [norm(v) for v in emb.embed_documents(DOCS)]
    dim = len(doc_vecs[0])
    correct, lat, in_sim, out_sim = 0, [], [], []
    n_faq = 0
    for q, gold in QUERIES:
        t = time.time(); qv = norm(emb.embed_query(q)); lat.append((time.time() - t) * 1000)
        sims = [cos(qv, d) for d in doc_vecs]
        top = max(range(len(sims)), key=lambda i: sims[i])
        if gold is None:
            out_sim.append(max(sims))
        else:
            n_faq += 1
            in_sim.append(sims[gold])
            correct += (top == gold)
    return {
        "model": model, "dim": dim,
        "acc": correct / n_faq,
        "lat_ms": sum(lat) / len(lat),
        "in_sim": sum(in_sim) / len(in_sim),
        "out_sim": sum(out_sim) / len(out_sim),
        "sep": sum(in_sim) / len(in_sim) - sum(out_sim) / len(out_sim),
    }


print(f"{'model':22}{'dim':>5}{'akurasi':>9}{'embed_ms':>10}{'sim_faq':>9}{'sim_oos':>9}{'pemisah':>9}")
for m in MODELS:
    try:
        r = run(m)
        print(f"{r['model']:22}{r['dim']:>5}{r['acc']:>8.0%}{r['lat_ms']:>9.0f}ms{r['in_sim']:>9.2f}{r['out_sim']:>9.2f}{r['sep']:>9.2f}")
    except Exception as e:
        print(f"{m:22} ERROR: {e}")
print("\nakurasi = query FAQ yang chunk benarnya rank #1 (10 query)")
print("sim_faq = kemiripan rata2 query FAQ ke chunk benar (tinggi=bagus)")
print("sim_oos = kemiripan tertinggi query out-of-scope (rendah=bagus, gampang ditolak)")
print("pemisah = sim_faq - sim_oos (makin besar makin gampang bedain in/out scope)")
print("EMBED_COMPARE_DONE")
