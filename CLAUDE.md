# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this workspace is

This is Kevin's working directory for the **Toti Cakery WhatsApp Chatbot** (a 3-person capstone; Kevin owns the Chatbot Service + WhatsApp integration only). Two things matter:

1. **`PROMPT_CLAUDE_CODE_TOTI_CAKERY_CHATBOT.md` is the authoritative spec.** Read it before doing chatbot work. It defines the full scope, rules, architecture, conversation flow, and a list of open questions (its section 17) that must be confirmed with Kevin before implementing the affected parts.
2. **The chatbot service does not exist yet.** As of now this directory contains only the spec and the reference backend. The chatbot (`chatbot-service/`, `services/payment-gateway/`, `whatsapp-gateway/`, `docker-compose.yml`, etc.) is still to be built per the spec's folder layout (spec §3).

## `Backend-Cakery/` is reference-only — do not modify

`Backend-Cakery/` is the teammate's (Nicholas's) FastAPI + PostgreSQL backend, included here as read-only reference (it is its own git repo). **Never edit it, and never add endpoints to it.** The chatbot talks to it over HTTP only. Building chatbot code is the entire job here.

### Critical gotcha: double-prefix routing bug in Backend-Cakery

Every router in `Backend-Cakery` declares its own `prefix=` *and* is re-included in `app/main.py` with another prefix. So the live paths are doubled, not what a casual read of the route files suggests:

| Logical intent | Router prefix | `main.py` include prefix | **Actual live path** |
|---|---|---|---|
| Products | `/products` | `/products` | `/products/products/` |
| FAQ | `/faq` | `/faq` | `/faq/faq` |
| Stock items | `/stock-items` | `/stock` | `/stock/stock-items/` |

The same doubling applies to every other router (auth, pricing, recipes, purchasing). **Do not hardcode raw paths read from the source.** Per spec §1.2: keep the base URL in config (`BACKEND_BASE_URL`) and verify real paths against the running backend's `/docs` or `/openapi.json` before relying on them; otherwise assume the clean (un-doubled) path and record the assumption in `MISSING_ENDPOINTS.md`.

### Backend endpoints: real vs. not-yet-built

- **Usable now** (buyer-relevant): products list/detail, FAQ list/detail, stock-items. `get_menu` / `get_product_detail` tools wire to these — `get_menu` is the one tool whose backend endpoint definitely exists, so it's the end-to-end smoke test (spec §15.6).
- **Not built yet** — orders, payments, customers, order status, human-takeover storage, financial reports. Do **not** invent these endpoints or fake responses. Implement them as clearly-marked mocks (`# MOCK — endpoint backend belum tersedia`) returning realistic dummy data, and log each one in `MISSING_ENDPOINTS.md` (name, assumed method+path, request/response shape, why). See spec §1, §5.

Product/FAQ response shapes live in `Backend-Cakery/app/schemas/product.py` and `faq.py` (note Indonesian field names: `nama_produk`, `harga_jual`, `deskripsi`, `kategori`, `pertanyaan`, `jawaban`).

## Hard rules from the spec (don't violate)

- **Midtrans is mock-only and isolated** in `services/payment-gateway/`. Never install `midtransclient`, never call the real Midtrans API, never put real credentials anywhere. The real impl is Nicholas's job later — so document the expected contract for an easy swap (spec §11).
- **RAG scope guard**: if retrieval similarity is below the configurable threshold, the bot must refuse to answer from general LLM knowledge and reply that it only serves Toti Cakery topics (spec §7). Threshold is a named config var, never hardcoded.
- **Product data is not embedded into Chroma** — only FAQ files are. Product info is fetched live via tools so prices/stock don't go stale (spec §7).
- The chatbot's own SQLite DB (sessions, cart drafts, conversation log, pending orders) is internal storage — that is *not* "adding a backend endpoint" and is allowed (spec §14).
- Build iteratively: skeleton + WhatsApp echo first, then RAG, then tools one at a time (spec §1.6). Don't generate everything in one giant file.

## Planned stack (fixed — see spec §2)

Python 3.11+ / FastAPI, LangChain, Ollama (`qwen3:1.7b` LLM + `qwen3-embedding:0.6b`), ChromaDB (persistent), SQLite via SQLAlchemy, `avoylenko/wwebjs-api` (Node, Docker) as the WhatsApp gateway (configure it, never rewrite it). Whole stack runs via `docker-compose`.

## Commands

The chatbot service has no code yet, so it has no build/test commands. Once scaffolded, the spec expects:

```bash
docker-compose up                       # whole stack: chatbot-service, chroma, wwebjs-api (+ollama if needed)
python chatbot-service/knowledge_base/ingest.py   # (re)embed FAQ files into ChromaDB (idempotent)
```

Reference backend (run only if you need to verify real endpoints/`/docs`):

```bash
# in Backend-Cakery/, needs Python 3.12+, PostgreSQL 17+, a .env with database_url
pip install -r requirements.txt
uvicorn app.main:app --reload          # Swagger at /docs, schema at /openapi.json
```
