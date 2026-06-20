# Payment Gateway (MOCK Midtrans)

Isolated mock of the payment provider (PROMPT §11). It contains **no real Midtrans
SDK, no credentials, and never calls Midtrans**. The chatbot depends only on the
contract below — when the backend team builds the real Midtrans integration, it
must honour the same request/response shapes so `chatbot-service` needs no changes.

## Run

```bash
# standalone
cd services/payment-gateway
pip install -r requirements.txt
uvicorn mock_server:app --port 9000

# or via docker compose (service name: payment-gateway)
```

## Contract (what the real implementation must provide)

### Create transaction
`POST /transactions`
```json
// request
{ "order_id": "INV-20260621-12345", "amount": 150000,
  "customer_name": "Budi", "customer_phone": "628123456789" }

// response
{ "transaction_id": "MOCK-AB12CD34EF", "order_id": "INV-20260621-12345",
  "qr_url": "https://.../qr.png", "va_number": "123456789012",
  "bank": "bca", "amount": 150000,
  "expiry_time": "2026-06-21T10:30:00+00:00", "status": "pending" }
```

### Get status
`GET /transactions/{order_id}` → `{ "order_id": str, "status": "pending"|"paid"|"expired"|"failed" }`

### Debug helper (mock only — remove in real impl)
`POST /debug/mark-paid/{order_id}` → force status to `paid` for manual testing.

## Expected behaviour of the REAL Midtrans implementation

- **Auth**: server key (Basic auth) for Snap/Core API; never expose it to the chatbot.
- **QR / VA**: return a real QRIS image URL and/or VA number from Midtrans Core API.
- **Webhook**: Midtrans posts payment notifications to a backend HTTP notification
  URL with a `signature_key` (SHA512 of `order_id+status_code+gross_amount+ServerKey`)
  that MUST be verified. The backend then updates order status; the chatbot can keep
  polling `GET /transactions/{order_id}` or be notified — either works as long as the
  status shape above is preserved.
- **Status mapping**: map Midtrans `transaction_status`
  (`settlement`/`capture` → `paid`, `expire` → `expired`, `deny`/`cancel` → `failed`,
  `pending` → `pending`).

## How the chatbot uses it

`chatbot-service/app/payment/client.py` calls `POST /transactions` at checkout and
the background worker polls `GET /transactions/{order_id}` to detect payment
(`app/conversation/background.py`).
