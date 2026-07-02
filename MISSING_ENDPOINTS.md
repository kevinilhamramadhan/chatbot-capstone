# Backend Endpoints — Status (chatbot view)

Status of every backend capability the chatbot depends on. The chatbot now talks
to the **real backend** for everything below (`app/backend_client/api.py`); the
only remaining mock is the low-priority Owner reports pair.

> Findings & small backend fixes for Nicholas live in `UNTUK_NICHOLAS_backend_todo.txt`.
> This file is the chatbot-side mirror.

Last synced against `Nicholl2/Backend-Cakery` @ commit `abd7241` (CORS Middleware).

---

## ✅ Built & live-verified (chatbot wired to real HTTP)

| Capability | Endpoint (live) | Notes |
|---|---|---|
| Double-prefix fix | `GET /products/`, `/faq`, … | clean paths |
| Product image | `ProductOut.image_url` | chatbot sends photo when populated |
| Service auth | `require_service_key` (`X-Service-Key`) | chatbot sends it on every call |
| Get customer | `GET /customers?nomor_wa=` | → `CustomerOut` |
| Upsert customer | `POST /customers` | → `CustomerOut` |
| Create order (B2) | `POST /orders` | → `OrderOut`; deducts recipe stock (optimistic locking); 409 active bill, 400 insufficient stock |
| Order status (B3) | `GET /orders/latest?nomor_wa=` | → `OrderOut`; 404 if none |
| Cancel order (B4) | `POST /orders/{order_id}/cancel` | 409 if already paid/partial |
| Payment (B5) | `POST /payments`, `GET /payments/{order_id}/status`, `POST /payments/notify` | **real Midtrans charge** (sandbox now; prod = backend env flip) |
| Takeover (C1) | `POST`/`GET /customers/{nomor_wa}/takeover` | → `TakeoverStatus` |
| Takeover handlers (C2) | `GET /admin/takeover-handlers` | → `{"numbers":[...]}`; chatbot falls back to `ADMIN_WA_NUMBER` when empty |
| Availability (C3) | `ProductOut.is_available` | computed recipe-vs-stock; `get_menu`/`add_to_cart` consume it |
| Ready push (C4) | backend POSTs `→ {CHATBOT_URL}/webhook/internal/orders/{id}/ready` on status=ready | receiver tested live |
| Order status update (C5) | `PATCH /orders/{order_id}/status` (admin JWT) | triggers C4; **C5→C4 chain live-verified** |

**Field/contract deltas handled in the adapter** (`app/backend_client/api.py`):
- `CustomerOut`/`OrderOut` use `id` (not `customer_id`/`order_id`); invoice number is
  nested at `OrderOut.invoice.nomor_invoice`.
- **Payment charge** (`POST /payments`) body is `{order_id, payment_type, amount}`
  where `payment_type ∈ {bank_transfer, qris}` = the **Midtrans channel** (NOT
  DP/Final — that's conveyed via `amount`). `GET /payments/{id}/status` returns
  `{order_id, invoice_status, amount_paid, amount_due, payments[]}`.
- `nomor_wa` is stored/queried in gateway chat-id form (`628…@c.us`) consistently.
- C4: backend env `CHATBOT_URL` must point at the chatbot (e.g. `http://localhost:8000`).

## ⚠️ Known backend nits (reported to Nicholas, chatbot unaffected/tolerant)
- `PATCH /orders/{id}/status` returns 500 (lazy-load serialization) even though the
  status change + C4 push succeed.
- `POST /orders/{id}/cancel` does not restore the recipe stock deducted at create.

---

## ❌ Still NOT built (chatbot ready & waiting)

### Owner reports — `GET /reports/summary` (the ONE endpoint still awaited)
- Contract: `GET /reports/summary?start_date&end_date` (service key) →
  `{revenue, expenses, order_count, avg_order_value, top_products[]}`.
- Chatbot side is **done**: `financial_report` / `business_analytics` call it for
  real (no more dummy data); while it 404s they reply honestly that the report
  isn't available yet. Ships in the backend → works with zero chatbot changes.

### Conversation log mirror — `POST /chatbot/conversations` (ERD C300 Tabel 3.20)
- Contract: `{nomor_wa, session_id, message, response, intent}` (service key) →
  stored in the backend's `chatbot_conversations` table (customer resolved from
  `nomor_wa`, minimal row created if unknown).
- Chatbot side is **done**: every replied turn is mirrored fire-and-forget; while
  the endpoint is missing it silently no-ops and the local SQLite log remains
  the record.

### Owner sets takeover handler (Admin Site concern, not chatbot)
- `PATCH /users/{user_id}/takeover-handler` — column + read endpoint exist; the
  Owner-facing setter doesn't. Chatbot works without it.

---

## Chatbot-service endpoints exposed to the team (no backend action needed)
- `POST /webhook/chat` — **Buyer Site web-chat widget** (C300 komponen C6/C7).
  Body `{nomor_wa, message}` (+ `X-Service-Key` header) →
  `{reply, media[], suppressed}`. Same session/tools/flow as WhatsApp.
- `POST /webhook/internal/orders/{order_id}/ready` — receiver for C4 push (idempotent).
- `POST /webhook/internal/takeover/{phone}/deactivate` — manual takeover reset.
  (Admin Site can also just set takeover inactive via the backend — the chatbot
  now re-checks the backend before suppressing, so it un-suppresses on its own.)
