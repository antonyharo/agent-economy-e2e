from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class CheckoutStatus(StrEnum):
    CREATED = "created"
    PAYMENT_PENDING = "payment_pending"
    PAID = "paid"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class ShippingAddress(BaseModel):
    street: str
    number: str
    city: str
    state: str
    postal_code: str
    country: str = "BR"


class CheckoutItem(BaseModel):
    product_id: str
    variant_id: str | None = None
    unit_price: float
    quantity: int


class Checkout(BaseModel):
    id: str
    cart_id: str
    items: list[CheckoutItem]
    shipping_option: str
    payment_method: str
    subtotal: float
    shipping: float
    discount: float
    total: float
    currency: str = "BRL"
    status: CheckoutStatus = CheckoutStatus.PAYMENT_PENDING
    payment_id: str | None = None
    order_id: str | None = None


class CheckoutView(BaseModel):
    checkout_id: str
    subtotal: float
    shipping: float
    discount: float
    total: float
    currency: str
    payment_method: str
    status: CheckoutStatus


SHIPPING_RATES: dict[str, float] = {
    "standard": 20.0,
    "express": 45.0,
}
