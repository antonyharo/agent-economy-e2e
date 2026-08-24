from __future__ import annotations

from pydantic import BaseModel, Field


class ProductVariant(BaseModel):
    id: str
    name: str
    available: bool = True


class Product(BaseModel):
    id: str
    name: str
    description: str = ""
    price: float
    currency: str = "BRL"
    available: bool = True
    category: str = ""
    variants: list[ProductVariant] = Field(default_factory=list)


class ProductSearchFilters(BaseModel):
    category: str | None = None
    min_price: float | None = None
    max_price: float | None = None
    available: bool | None = None


class ProductSummary(BaseModel):
    id: str
    name: str
    price: float
    currency: str
    available: bool
    category: str
    variants: list[ProductVariant]


class ProductSearchResult(BaseModel):
    products: list[ProductSummary]
    next_cursor: str | None = None
