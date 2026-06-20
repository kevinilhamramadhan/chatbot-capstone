"""HTTP client the chatbot uses to talk to the payment gateway service.

Points at PAYMENT_GATEWAY_URL, which is the MOCK Midtrans service today and the
real one later — the chatbot code doesn't change when it's swapped.
"""

import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class PaymentClient:
    def __init__(self) -> None:
        self._base = settings.payment_gateway_url.rstrip("/")

    async def create_transaction(
        self, order_id: str, amount: float, customer_name: str, customer_phone: str
    ) -> dict:
        payload = {
            "order_id": order_id,
            "amount": amount,
            "customer_name": customer_name,
            "customer_phone": customer_phone,
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(f"{self._base}/transactions", json=payload)
            resp.raise_for_status()
            return resp.json()

    async def get_status(self, order_id: str) -> str:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{self._base}/transactions/{order_id}")
            if resp.status_code == 404:
                return "pending"
            resp.raise_for_status()
            return resp.json().get("status", "pending")


payment_client = PaymentClient()
