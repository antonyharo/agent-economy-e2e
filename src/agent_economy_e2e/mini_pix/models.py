from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Status = Literal["PENDING", "COMPLETED", "FAILED"]


def _amount(value: Decimal) -> Decimal:
    if value <= 0:
        raise ValueError("amount must be positive")
    return value.quantize(Decimal("0.01"))


class Charge(BaseModel):
    model_config = ConfigDict(extra="ignore")

    pix_code: str
    charge_id: str
    transaction_id: str
    receiver_account_id: str
    amount: Decimal
    currency: Literal["BRL"] = "BRL"
    status: Status = "PENDING"

    _validate_amount = field_validator("amount")(_amount)


class Transaction(BaseModel):
    transaction_id: str
    currency: Literal["BRL"] = "BRL"
    status: Status = "PENDING"


class Invoice(BaseModel):
    invoice_id: str
    transaction_id: str
    amount: Decimal
    currency: Literal["BRL"] = "BRL"
    status: Literal["COMPLETED"] = "COMPLETED"


class CreateChargeRequest(BaseModel):
    txid: str = Field(min_length=1)
    receiver_account_id: str = Field(min_length=1)
    amount: Decimal
    currency: Literal["BRL"] = "BRL"

    _validate_amount = field_validator("amount")(_amount)


class ResolveRequest(BaseModel):
    pix_code: str = Field(min_length=1)


class CompleteRequest(BaseModel):
    transaction_id: str = Field(min_length=1)


class TransactionRequest(BaseModel):
    transaction_id: str = Field(min_length=1)
