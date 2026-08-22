from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class PaymentStatus(StrEnum):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    EXPIRED = "expired"


class Payment(BaseModel):
    id: str
    checkout_id: str
    method: str = "pix"
    amount: float
    currency: str = "BRL"
    pix_code: str
    status: PaymentStatus = PaymentStatus.PENDING


class PaymentInstructions(BaseModel):
    payment_id: str
    method: str
    amount: float
    currency: str
    pix_code: str
    status: PaymentStatus


class PaymentStatusView(BaseModel):
    payment_id: str
    checkout_id: str
    status: PaymentStatus
    amount: float
    currency: str
