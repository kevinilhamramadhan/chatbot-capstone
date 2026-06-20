# Toti Cakery — WhatsApp Chatbot Service

RAG + tool-calling WhatsApp chatbot for Toti Cakery (a bakery). Built with FastAPI,
LangChain, Ollama (`qwen3:1.7b`), ChromaDB, and the `avoylenko/wwebjs-api` WhatsApp
gateway. This repo is **only** the chatbot + WhatsApp integration — the main backend
(`Backend-Cakery/`, reference-only) and the React frontends are owned by teammates.

> Scope, rules, and the full conversation flow live in
> `PROMPT_CLAUDE_CODE_TOTI_CAKERY_CHATBOT.md`. Endpoints the backend still owes us
> are in `MISSING_ENDPOINTS.md`. See `CLAUDE.md` for an orientation aimed at AI agents.

## Architecture

```
Customer (WhatsApp)
   ▼
wwebjs-api (Docker) ──webhook──▶ chatbot-service /webhook/whatsapp
                                       │  orchestrator (state machine)
              ┌────────────────────────┼─────────────────────────┐
              ▼                         ▼                          ▼
        rag/ (ChromaDB +          tools/ (LangChain          backend_client/
        qwen3-embedding)          tool calling)              (real: products/faq;
              │                         │                     mock: orders/customers)
              ▼                         ▼
        llm/ (Ollama qwen3:1.7b, tool calling)        payment/ ─▶ services/payment-gateway (MOCK)
```

- **Real** today: `get_menu`, `get_product_detail`, `compare_products` (live backend
  products), plus FAQ RAG. **Mocked** (endpoints not built yet): order create,
  order status, customers, payments (mock Midtrans), human-takeover storage, reports.
- The chatbot keeps its **own SQLite DB** (sessions, conversation log, pending orders).

## Prerequisites

1. **Docker + Docker Compose**.
2. **Ollama** running with the models pulled:
   ```bash
   ollama pull qwen3:1.7b
   ollama pull qwen3-embedding:0.6b
   ```
   By default the chatbot reaches Ollama on the host via `host.docker.internal`.
3. The **backend** (`Backend-Cakery`) running somewhere reachable, for the real
   product/FAQ tools. Set `BACKEND_BASE_URL` to it. (The chatbot degrades gracefully
   if it's down — product tools just return "menu sedang tidak bisa diambil".)

## Setup

```bash
cp .env.example .env          # then edit values (ADMIN_WA_NUMBER, BACKEND_BASE_URL, ...)
docker compose up --build
```

This starts: `chatbot-service` (:8000), `payment-gateway` mock (:9000),
`wwebjs-api` (:3000). Chroma runs embedded inside chatbot-service.

### 1. Ingest the knowledge base (FAQ → ChromaDB)

```bash
docker compose exec chatbot-service python knowledge_base/ingest.py
# or locally:  cd chatbot-service && python knowledge_base/ingest.py
```
Re-run anytime — it's idempotent (re-embeds changed files, drops deleted ones).

### 2. Link WhatsApp (one-time, manual)

```bash
# start the session
curl http://localhost:3000/session/start/toti -H "x-api-key: $WWEBJS_API_KEY"
# open the QR image in a browser and scan it from WhatsApp on your phone
xdg-open "http://localhost:3000/session/qr/toti/image?x-api-key=$WWEBJS_API_KEY"
```
The session id (`toti`) comes from `WWEBJS_SESSION_ID`. Auth persists in
`whatsapp-gateway/sessions/` so you won't need to re-scan after restarts.

## Testing it

### Fastest: local CLI (no phone/WhatsApp needed)

Drives the full brain (RAG + tools + order flow) via the terminal; outbound WA
sends are stubbed. Needs Ollama running (and the backend, for real product tools):

```bash
cd chatbot-service
python knowledge_base/ingest.py        # once, to populate ChromaDB
python -m scripts.chat_cli             # then just chat; /state to inspect, /quit
```

### Full stack (real WhatsApp)

- **Smoke test (real tool):** message the bot **"menu apa aja"** → it calls the real
  `get_menu` and replies with live products + prices.
- **Order flow:** "mau pesan brownies 2" → confirm ("sudah sesuai") → give name &
  address → pickup/delivery → confirm phone → choose full/DP → receive VA + QR.
- **Simulate payment:** the gateway is mock, so flip it manually:
  ```bash
  curl -X POST http://localhost:9000/debug/mark-paid/<NOMOR_INVOICE>
  ```
  Within `PAYMENT_CHECK_INTERVAL_SECONDS` the bot proactively confirms payment.
- **Mark order ready (proactive pickup/delivery msg):**
  ```bash
  curl -X POST http://localhost:8000/webhook/internal/orders/<id>/ready
  ```
- **End human takeover (manual):**
  ```bash
  curl -X POST http://localhost:8000/webhook/internal/takeover/<phone>/deactivate
  ```

## Unit tests

```bash
cd chatbot-service
pip install -r requirements.txt
pytest
```

## Key configuration (`.env`)

| Var | Meaning |
|---|---|
| `BACKEND_BASE_URL` | Base URL of Nicholas's backend (paths resolved defensively) |
| `OLLAMA_BASE_URL` | Ollama endpoint (LLM + embeddings) |
| `RAG_SIMILARITY_THRESHOLD` | Below this, the bot refuses out-of-topic questions (tune me) |
| `ADMIN_WA_NUMBER` | Single admin number for escalation notifications |
| `ALLOW_DOWN_PAYMENT` / `DOWN_PAYMENT_PERCENTAGE` | Enable DP 50% at checkout |
| `PAYMENT_TIMEOUT_MINUTES` / `PAYMENT_CHECK_INTERVAL_SECONDS` | Payment timeout + poll cadence |
| `STORE_NAME` / `STORE_ADDRESS` | Used in pickup/delivery messages |

## Decisions baked in (confirmed with Kevin)

- **Checkout phone** auto-fills from the sender's WhatsApp number (overridable).
- **Payment**: supports full payment **and** DP 50%.
- **Admin**: single fixed `ADMIN_WA_NUMBER`.
- **RAG threshold**: a single config var (`RAG_SIMILARITY_THRESHOLD`), not hardcoded.
