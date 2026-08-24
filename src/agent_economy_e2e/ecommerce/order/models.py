from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from agent_economy_e2e.ecommerce.checkout.models import CheckoutItem, ShippingAddress


class OrderStatus(StrEnum):
    CONFIRMED = "confirmed"


class Order(BaseModel):
    id: str
    checkout_id: str
    payment_id: str
    status: OrderStatus = OrderStatus.CONFIRMED
    items: list[CheckoutItem] = Field(default_factory=list)
    shipping_address: ShippingAddress | None = None
    total: float
    currency: str = "BRL"


class OrderConfirmation(BaseModel):
    order_id: str
    checkout_id: str
    payment_id: str
    status: OrderStatus
    shipping_address: ShippingAddress | None = None
