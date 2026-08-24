from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class AuthorizePaymentRequest(BaseModel):
    agent_id: str = Field(min_length=1)
    payer_account_id: str = Field(min_length=1)
    pix_code: str = Field(min_length=1)
    amount: Decimal
    reference_id: str = Field(min_length=1)
    category: str | None = None
    categories: list[str] = Field(default_factory=list)
    currency: Literal["BRL"] = "BRL"

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("amount must be positive")
        return value.quantize(Decimal("0.01"))
