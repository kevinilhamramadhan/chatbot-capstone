# Backend Endpoints — Status (chatbot view)

Status of every backend capability the chatbot depends on. Items still missing are
**mocked** in the chatbot (`app/backend_client/mock_backend.py`, marked `# MOCK`);
swap each mock for a real HTTP call once its endpoint ships.

> The exact build spec sent to Nicholas lives in `UNTUK_NICHOLAS_backend_todo.txt`
> (that file is the source of truth for what's left). This file is the chatbot-side
> mirror.

Last synced against `Nicholl2/Backend-Cakery` @ commit `62c9838` (Test Order by Chatbot).

---

## ✅ Built & verified working

| Capability | Endpoint (live) | Notes |
|---|---|---|
| Double-prefix fix | `GET /products/`, `/faq`, … | clean paths; chatbot resolves automatically |
| Product image | `ProductOut.image_url` | chatbot sends product photo when populated |
| Service auth | `require_service_key` (`X-Service-Key`) | chatbot sends it on every backend call |
| Get customer | `GET /customers?nomor_wa=` | → `CustomerOut` |
| Upsert customer | `POST /customers` | → `CustomerOut` |
| Create order | `POST /orders` | → `OrderOut` (incl. nested `invoice`) |
| Set takeover | `POST /customers/{nomor_wa}/takeover` | → `TakeoverStatus` |
| Get takeover | `GET /customers/{nomor_wa}/takeover` | → `TakeoverStatus` (`is_expired`) |

**Field-mapping deltas for the eventual swap** (adapter layer only, tools unchanged):
- `CustomerOut` returns `id` (not `customer_id`) → map `id` → `customer_id`.
- `OrderOut` returns order id as `id`, invoice number as `invoice.nomor_invoice`
  (nested) → map accordingly.
- `created_via` default is `"chatbot"` (lowercase).

These are all still **mocked** in `mock_backend.py` today; the swap is ~1 line per
function once we decide to wire them (see `UNTUK_NICHOLAS_backend_todo.txt` notes).

---

## ❌ Not built yet (chatbot still mocks / works around these)

### B3 — get_order_status
- Expected: `GET /orders?nomor_wa={wa}` → latest order as `OrderOut` (incl. `invoice`); 404 if none.
- Now: chatbot reads its **local** `pending_orders` table.

### B4 — cancel_order
- Expected: `POST /orders/{order_id}/cancel` → `OrderOut` (status `cancelled`); 409 if already paid.
- Now: chatbot cancels in its **local** table.

### C3 — product availability (`is_available`)
- Expected: computed `is_available: bool` on `ProductOut` (recipe vs `stock_items`),
  and rejected in `POST /orders` when out of stock.
- Now: chatbot treats missing field as available; `get_menu`/`add_to_cart` already
  consume `is_available` once present.

### B5 — payments + Midtrans
- Expected (all in backend): `POST /payments`, `GET /payments/{order_id}/status`,
  `POST /payments/notify` (Midtrans webhook). Supports `DP`/`Final`;
  updates `invoices.status` (`partial`/`paid`).
- Now: chatbot uses the local **MOCK** gateway (`services/payment-gateway`); will
  point `PAYMENT_GATEWAY_URL` at the backend when ready. No Midtrans keys in chatbot.

### C2 — admin takeover-handlers (dynamic via RBAC)
- Expected: `GET /admin/takeover-handlers` (service key) → `{ "numbers": [...] }`
  (users with `handles_takeover=true`); Owner sets it via Admin Site.
- Now: chatbot calls it (mock → `[]`) and falls back to env `ADMIN_WA_NUMBER`.

### C4 — push "ready" → chatbot
- Expected: when an order's status becomes `ready`, backend `POST`s to
  `{CHATBOT_URL}/webhook/internal/orders/{order_id}/ready` (receiver already exists).
- Now: triggered manually via that internal endpoint. ("paid" is not pushed —
  chatbot detects it by polling B5b.)

### Owner reports (low priority)
- Expected: `GET /reports/financial`, `GET /reports/analytics` (Owner only).
- Now: `financial_report` / `business_analytics` tools return **MOCK** dummy data.

---

## Internal chatbot endpoints (no backend action needed)
- `POST /webhook/internal/orders/{order_id}/ready` — receiver for C4 push.
- `POST /webhook/internal/takeover/{phone}/deactivate` — manual takeover reset.
