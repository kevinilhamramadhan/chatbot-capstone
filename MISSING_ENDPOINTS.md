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

## 1b. Product image field (just needs exposing on the existing endpoint)

- The data model (C300 Tabel 3.4, tabel `products`) **already defines
  `image_url VARCHAR(255)`**, but the live `ProductOut` schema in
  `Backend-Cakery/app/schemas/product.py` does **not** return it (fields: id,
  nama_produk, deskripsi, kategori, hpp_total, harga_jual, markup_percentage,
  is_active, created_at, updated_at).
- Impact: `get_product_detail` cannot send a product photo (PROMPT §10.2). The
  chatbot already degrades gracefully (text only) and will send photos
  automatically once `image_url` is present on the response.
- Needed (small): add `image_url: str | None` to `ProductOut` (the column exists).

## 1c. Finished-product stock (data-model gap to confirm)

- `get_menu` mentions "ketersediaan stok", but the `products` table has **no
  stock/quantity column** — stock only exists for raw materials (`stock_items`).
- For now `get_menu` reports availability via `is_active` only. Confirm whether
  finished-product availability should be derived (recipe vs `stock_items`) or a
  simple `is_available`/`stock_qty` column added to `products`.

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

### set_takeover
- Method/path diasumsikan: `POST /customers/{nomor_wa}/takeover`
- Request body diasumsikan: `{ "active": bool, "expires_at": ISO-8601 | null }`
- Alasan: menyimpan status human-takeover di tabel `customers`. Field penyimpanan
  ini belum jelas ada — perlu dikonfirmasi.
- Sementara: status disimpan lokal di chatbot (tabel `sessions`), reset manual lewat
  `POST /webhook/internal/takeover/{phone}/deactivate`.

### admin number lookup
- Diharapkan: cara mengambil nomor WA admin secara dinamis dari backend.
- Sementara: pakai env `ADMIN_WA_NUMBER` (satu nomor fix).

## 5. Owner reports (prioritas rendah)

### financial_report / business_analytics
- Method/path diasumsikan: `GET /reports/financial`, `GET /reports/analytics` (Owner only)
- Response diasumsikan: data agregat (pendapatan, pengeluaran, produk terlaris, dll).
- Alasan: tool khusus Owner. Saat ini mengembalikan data dummy.

---

## Routing note (double-prefix bug)

`Backend-Cakery/app/main.py` meng-`include_router` setiap router dengan prefix yang
**sama** dengan prefix bawaan router-nya, sehingga path menjadi ganda:

| Endpoint dipakai chatbot | Path "bersih" (asumsi) | Path live saat ini (akibat bug) |
|---|---|---|
| List produk | `GET /products/` | `GET /products/products/` |
| Detail produk | `GET /products/{id}` | `GET /products/products/{id}` |
| List FAQ | `GET /faq` | `GET /faq/faq` |

Chatbot mencoba path "bersih" dulu, lalu fallback ke path ganda, dan menyimpan mana
yang berhasil (`app/backend_client/base.py`). Jadi begitu bug diperbaiki, chatbot
tetap jalan tanpa perubahan. **Tetap disarankan memperbaiki bug ini di backend.**
