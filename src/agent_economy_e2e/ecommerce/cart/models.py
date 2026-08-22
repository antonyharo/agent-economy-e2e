from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class CartStatus(StrEnum):
    ACTIVE = "active"
    CHECKED_OUT = "checked_out"


class CartItem(BaseModel):
    product_id: str
    variant_id: str | None = None
    name: str
    unit_price: float
    quantity: int
    currency: str = "BRL"


class Cart(BaseModel):
    id: str
    agent_id: str = "default"
    status: CartStatus = CartStatus.ACTIVE
    items: list[CartItem] = Field(default_factory=list)


class CartTotals(BaseModel):
    cart_id: str
    subtotal: float
    shipping: float
    discount: float
    total: float
    currency: str = "BRL"
    items: list[CartItem]
