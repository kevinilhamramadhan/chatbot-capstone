# Backend Endpoints Needed by the Chatbot (to send to Nicholas)

This file lists every backend capability the chatbot needs that **does not exist
yet** in `Backend-Cakery`. Each is currently **mocked** in the chatbot
(`app/backend_client/mock_backend.py`, clearly marked `# MOCK`). Swap the mocks
for real HTTP calls once these endpoints ship.

It also records **path assumptions** caused by the backend's double-prefix routing
bug, which the chatbot works around defensively (see "Routing note" at the end).

---

## 1. Customers

### get_customer_by_wa
- Method/path diasumsikan: `GET /customers?nomor_wa={phone}`
- Response diasumsikan: `{ "customer_id": int, "nomor_wa": str, "nama": str, "alamat": str, "nomor_hp": str } | null`
- Alasan: cek apakah pelanggan sudah terdaftar saat checkout.

### upsert_customer
- Method/path diasumsikan: `POST /customers`
- Request body diasumsikan: `{ "nomor_wa": str, "nama": str, "alamat": str, "nomor_hp": str }`
- Response diasumsikan: `{ "customer_id": int, ...echo fields }`
- Alasan: menyimpan/memperbarui data pelanggan dari hasil checkout chatbot.

## 1b. Product image field — DONE ✓

- `image_url` is now returned by `ProductOut`. `get_product_detail` will send the
  product photo automatically (just make sure the column is actually populated).

## 1c. Finished-product availability — DECIDED: compute from recipe vs stock

- Decision (opsi b): a product is "available" if every ingredient in its `recipes`
  has enough quantity in `stock_items` to make ≥1 unit. No stock column added.
- Backend: add a computed `is_available: bool` to `ProductOut` (GET /products and
  /products/{id}), and reuse the same check in create_order (reject out-of-stock).
- Chatbot already consumes `is_available`: `get_menu` marks unavailable items and
  `add_to_cart` rejects them. (Missing field => treated as available.)

## 2. Orders

> Field names below follow the C300 data model (tabel `orders`, `order_items`,
> `invoices`, `payments`, `customers`). The chatbot maps its internal names to
> these (qty→`jumlah`, full/dp→`Final`/`DP`).

### create_order_chatbot  (C300 TOTI-13)
- Method/path diasumsikan: `POST /orders`
- Request body diasumsikan:
  `{ "customer_id": int,                      // dari upsert_customer
     "items": [ { "product_id": int, "jumlah": int } ],
     "metode_pengiriman": "pickup" | "delivery",
     "created_via": "ChatBot" }`
- Response diasumsikan:
  `{ "order_id": int, "nomor_invoice": str, "total_harga_pesanan": float, "status": "pending" }`
- Alasan: mencatat pesanan dari chatbot ke `orders` + `order_items` (dengan
  `hpp_snapshot`/`subtotal`) dan menerbitkan invoice.

### get_order_status  (C300 TOTI-18)
- Method/path diasumsikan: `GET /orders?nomor_wa={wa}` atau `GET /customers/{wa}/orders/latest`
- Response diasumsikan:
  `{ "order_id": int, "nomor_invoice": str,
     "order_status": "pending"|"in_process"|"ready"|"delivered"|"picked_up",
     "invoice_status": "unpaid"|"partial"|"paid"|"refunded" }`
- Alasan: pelanggan cek status. (Sementara status diambil dari DB lokal chatbot.)
- Catatan: status order mengikuti alur C200 (Pending → In Process → Ready →
  Delivered/Picked Up); invoice mengikuti ENUM `unpaid/partial/paid/refunded`.

### cancel_order
- Method/path diasumsikan: `POST /orders/{order_id}/cancel`
- Response diasumsikan: `{ "order_id": int, "status": "cancelled" }`
- Alasan: pelanggan membatalkan pesanan yang belum dibayar (refund penuh oleh
  penjual = TOTI-19 `process_refund`, di luar scope chatbot).

### order status -> "ready" trigger
- Diharapkan: webhook/endpoint dari Admin Site saat status pesanan jadi `ready`,
  agar chatbot bisa proaktif memberi tahu pelanggan.
- Sementara: dipicu manual lewat endpoint internal chatbot
  `POST /webhook/internal/orders/{order_id}/ready`.

## 3. Payments  (C300 TOTI-17 create_payment / TOTI-08 verify_payment)
- Ditangani lewat service `services/payment-gateway` (MOCK Midtrans). Implementasi
  real Midtrans = tanggung jawab backend. Kontrak ada di
  `services/payment-gateway/README.md`.
- Mendukung **DP 50% atau Final** (sesuai `payments.payment_type` ENUM `DP/Final`
  dan invoice ENUM `unpaid/partial/paid/refunded`). Chatbot mengirim pilihan
  `DP`/`Final` + nominal; backend yang membuat tagihan Midtrans dan meng-update
  `invoices.status` (partial saat DP, paid saat lunas).
- ⚠️ Perlu disepakati: siapa yang memanggil Midtrans — Chatbot Service langsung,
  atau Website Service via endpoint `POST /payments`? Mock ini bisa dipakai untuk
  kedua arsitektur (chatbot cukup menukar `PAYMENT_GATEWAY_URL`).

## 4. Human Takeover

### set_takeover  — DIPUTUSKAN: disimpan di backend (opsi b)
- Tambah kolom di tabel `customers`: `human_takeover_active BOOLEAN default false`,
  `takeover_expires_at TIMESTAMP null`.
- `POST /customers/{nomor_wa}/takeover` (service key)
  - body: `{ "active": bool, "expires_at": ISO-8601 | null }`
- `GET /customers/{nomor_wa}/takeover` (service key) — chatbot cek status.
- Endpoint admin (JWT) untuk mematikan takeover dari Admin Site.
- Chatbot sudah menulis status ini (kini ke mock) + reset manual via
  `POST /webhook/internal/takeover/{phone}/deactivate`; tinggal swap saat jadi.

### admin number lookup
- Diharapkan: cara mengambil nomor WA admin secara dinamis dari backend.
- Sementara: pakai env `ADMIN_WA_NUMBER` (satu nomor fix).

## 5. Owner reports (prioritas rendah)

### financial_report / business_analytics
- Method/path diasumsikan: `GET /reports/financial`, `GET /reports/analytics` (Owner only)
- Response diasumsikan: data agregat (pendapatan, pengeluaran, produk terlaris, dll).
- Alasan: tool khusus Owner. Saat ini mengembalikan data dummy.

---

## Routing note (double-prefix bug) — FIXED ✓

The backend removed the per-router prefixes, so paths are clean now:
`GET /products/`, `GET /products/{id}`, `GET /faq`. The chatbot tries the clean
path first (and still falls back to the doubled form just in case), so no chatbot
change was needed. Service auth: the chatbot now sends `X-Service-Key` on backend
calls (matches the backend's `require_service_key`).
