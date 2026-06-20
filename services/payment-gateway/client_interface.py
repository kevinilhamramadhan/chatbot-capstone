"""Abstract contract for the payment gateway.

The chatbot depends only on this interface. The current implementation is a mock
(`mock_server.py`); the real Midtrans implementation will be built by the backend
team later and must honour the exact same shapes. See README.md for the full
expected contract (auth, webhooks, Midtrans field mapping).
"""

from abc import ABC, abstractmethod
from typing import Literal, TypedDict

PaymentStatus = Literal["pending", "paid", "expired", "failed"]


class TransactionResult(TypedDict):
    transaction_id: str
    order_id: str
    qr_url: str
    va_number: str
    bank: str
    amount: float
    expiry_time: str  # ISO-8601
    status: PaymentStatus


class StatusResult(TypedDict):
    order_id: str
    status: PaymentStatus


class PaymentGatewayClient(ABC):
    @abstractmethod
    async def create_transaction(
        self,
        order_id: str,
        amount: float,
        customer_name: str,
        customer_phone: str,
    ) -> TransactionResult:
        ...

    @abstractmethod
    async def get_transaction_status(self, order_id: str) -> StatusResult:
        ...
