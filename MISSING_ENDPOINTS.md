# Backend Endpoints — Status (chatbot view)

Status of every backend capability the chatbot depends on. Items still missing are
**mocked** in the chatbot (`app/backend_client/mock_backend.py`, marked `# MOCK`);
swap each mock for a real HTTP call once its endpoint ships.

> The exact build spec sent to Nicholas lives in `UNTUK_NICHOLAS_backend_todo.txt`.
> This file is the chatbot-side mirror.

Last synced against `Nicholl2/Backend-Cakery` @ commit `0eac209` (Add Payment).

---

## ✅ Built on the backend (ready to wire)

| Capability | Endpoint (live) | Notes |
|---|---|---|
| Double-prefix fix | `GET /products/`, `/faq`, … | clean paths |
| Product image | `ProductOut.image_url` | chatbot sends photo when populated |
| Service auth | `require_service_key` (`X-Service-Key`) | chatbot must send it |
| Get customer | `GET /customers?nomor_wa=` | → `CustomerOut` |
| Upsert customer | `POST /customers` | → `CustomerOut` |
| Create order (B2) | `POST /orders` | → `OrderOut` (nested `invoice`) |
| **Order status (B3)** | `GET /orders/latest?nomor_wa=` | → `OrderOut`; 404 if none |
| **Cancel order (B4)** | `POST /orders/{order_id}/cancel` | |
| **Payment (B5)** | `POST /payments`, `GET /payments/{order_id}/status`, `POST /payments/notify` | **real Midtrans charge** |
| Takeover (C1) | `POST`/`GET /customers/{nomor_wa}/takeover` | → `TakeoverStatus` |
| **Ready push (C4)** | backend POSTs `→ {chatbot_url}/webhook/internal/orders/{id}/ready` on status=ready | receiver already in chatbot |

**Field/contract deltas for the swap** (adapter layer only — tools unchanged):
- `CustomerOut`/`OrderOut` use `id` (not `customer_id`/`order_id`); invoice number is
  nested at `OrderOut.invoice.nomor_invoice`.
- Order status path is `GET /orders/latest?nomor_wa=` (not `/orders?nomor_wa=`).
- **Payment charge** (`POST /payments`) body is `{order_id, payment_type, amount}`
  where `payment_type ∈ {bank_transfer, qris}` = the **Midtrans channel** (NOT
  DP/Final). DP-vs-full is conveyed via `amount`. `GET /payments/{id}/status`
  returns `{order_id, status, amount_paid, amount_due, payments[]}`.
- C4: set the backend's `CHATBOT_URL` to the chatbot's address so the ready-push lands.

These are still **mocked** in `mock_backend.py` today; swapping them to real HTTP is
Kevin's small adapter change (no tool/flow changes).

---

## ❌ Still NOT built (chatbot mocks / works around)

### C2 — admin takeover-handlers (dynamic via RBAC)
- Expected: `GET /admin/takeover-handlers` (service key) → `{ "numbers": [...] }`
  (users with `handles_takeover=true`); Owner sets it via Admin Site.
- Now: chatbot calls it (mock → `[]`) and falls back to env `ADMIN_WA_NUMBER`.

### C3 — product availability (`is_available`)
- Expected: computed `is_available: bool` on `ProductOut` (recipe vs `stock_items`),
  and reject out-of-stock items in `POST /orders`.
- Now: chatbot treats a missing field as available; `get_menu`/`add_to_cart` already
  consume `is_available` once present.

### Owner reports (low priority)
- Expected: `GET /reports/financial`, `GET /reports/analytics` (Owner only).
- Now: `financial_report` / `business_analytics` tools return **MOCK** dummy data.

---

## Internal chatbot endpoints (no backend action needed)
- `POST /webhook/internal/orders/{order_id}/ready` — receiver for C4 push.
- `POST /webhook/internal/takeover/{phone}/deactivate` — manual takeover reset.
