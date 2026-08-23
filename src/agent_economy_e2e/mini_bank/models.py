from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator


def positive_amount(value: Decimal) -> Decimal:
    if value <= 0:
        raise ValueError("amount must be positive")
    return value.quantize(Decimal("0.01"))


class Account(BaseModel):
    account_id: str
    balance: Decimal
    currency: Literal["BRL"] = "BRL"


class BalanceResponse(Account):
    pass


class AccountOperation(BaseModel):
    account_id: str = Field(min_length=1)
    amount: Decimal
    transaction_id: str = Field(min_length=1)
    currency: Literal["BRL"] = "BRL"

    _validate_amount = field_validator("amount")(positive_amount)


class PixPayment(BaseModel):
    pix_code: str = Field(min_length=1)
    payer_account_id: str = Field(min_length=1)
    amount: Decimal
    currency: Literal["BRL"] = "BRL"

    _validate_amount = field_validator("amount")(positive_amount)


class CreateChargeRequest(BaseModel):
    receiver_account_id: str = Field(min_length=1)
    amount: Decimal
    currency: Literal["BRL"] = "BRL"

    _validate_amount = field_validator("amount")(positive_amount)
