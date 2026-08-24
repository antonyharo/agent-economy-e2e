from __future__ import annotations

import json
import os
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException

from .models import (
    Charge,
    CompleteRequest,
    CreateChargeRequest,
    Invoice,
    ResolveRequest,
    Transaction,
    TransactionRequest,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data" / "mini-pix"


def _json_default(value: Any) -> str:
    if isinstance(value, Decimal):
        return format(value, ".2f")
    raise TypeError(f"unsupported value: {type(value)!r}")


def _read(path: Path, default: list[dict[str, Any]]) -> list[dict[str, Any]]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(json.dumps(default, indent=2), encoding="utf-8")
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, records: list[dict[str, Any]]) -> None:
    path.write_text(
        json.dumps(records, indent=2, default=_json_default), encoding="utf-8"
    )


def _dump(model: Any) -> dict[str, Any]:
    return model.model_dump(mode="json")


def create_charge(
    txid: str,
    receiver_account_id: str,
    amount: Decimal,
    data_dir: Path | None = None,
) -> Charge:
    directory = data_dir or DEFAULT_DATA_DIR
    path = directory / "charges.json"
    charges = _read(path, [])
    for record in charges:
        if record["transaction_id"] == txid:
            return Charge.model_validate(record)
    charge = Charge(
        pix_code=f"PIX-{uuid4().hex[:16].upper()}",
        charge_id=f"charge-{uuid4().hex[:12]}",
        transaction_id=txid,
        receiver_account_id=receiver_account_id,
        amount=amount,
    )
    charges.append(_dump(charge))
    _write(path, charges)
    transactions = _read(directory / "transactions.json", [])
    transactions.append(_dump(Transaction(transaction_id=txid)))
    _write(directory / "transactions.json", transactions)
    return charge


def resolve_pix_code(pix_code: str, data_dir: Path | None = None) -> Charge:
    records = _read((data_dir or DEFAULT_DATA_DIR) / "charges.json", [])
    for record in records:
        if record["pix_code"] == pix_code:
            return Charge.model_validate(record)
    raise ValueError("pix_code not found")


def complete_transaction(
    transaction_id: str,
    data_dir: Path | None = None,
) -> Transaction:
    directory = data_dir or DEFAULT_DATA_DIR
    path = directory / "transactions.json"
    transactions = _read(path, [])
    for index, record in enumerate(transactions):
        if record["transaction_id"] != transaction_id:
            continue
        transaction = Transaction.model_validate(record)
        if transaction.status == "COMPLETED":
            return transaction
        if transaction.status == "FAILED":
            raise ValueError("transaction already failed")
        transaction.status = "COMPLETED"
        transactions[index] = _dump(transaction)
        _write(path, transactions)
        charges = _read(directory / "charges.json", [])
        for charge_index, charge in enumerate(charges):
            if charge["transaction_id"] == transaction_id:
                charge["status"] = "COMPLETED"
                charges[charge_index] = charge
        _write(directory / "charges.json", charges)
        return transaction
    raise ValueError("transaction not found")


def generate_invoice(transaction_id: str, data_dir: Path | None = None) -> Invoice:
    directory = data_dir or DEFAULT_DATA_DIR
    transactions = _read(directory / "transactions.json", [])
    transaction = next(
        (
            Transaction.model_validate(item)
            for item in transactions
            if item["transaction_id"] == transaction_id
        ),
        None,
    )
    if transaction is None:
        raise ValueError("transaction not found")
    if transaction.status != "COMPLETED":
        raise ValueError("invoice requires a completed transaction")
    charges = _read(directory / "charges.json", [])
    charge = next(
        (
            Charge.model_validate(item)
            for item in charges
            if item["transaction_id"] == transaction_id
        ),
        None,
    )
    if charge is None:
        raise ValueError("charge not found")
    path = directory / "invoices.json"
    invoices = _read(path, [])
    for record in invoices:
        if record["transaction_id"] == transaction_id:
            return Invoice.model_validate(record)
    invoice = Invoice(
        invoice_id=f"invoice-{uuid4().hex[:12]}",
        transaction_id=transaction_id,
        amount=charge.amount,
    )
    invoices.append(_dump(invoice))
    _write(path, invoices)
    return invoice


def fail_transaction(transaction_id: str, data_dir: Path | None = None) -> Transaction:
    directory = data_dir or DEFAULT_DATA_DIR
    path = directory / "transactions.json"
    transactions = _read(path, [])
    for index, record in enumerate(transactions):
        if record["transaction_id"] == transaction_id:
            transaction = Transaction.model_validate(record)
            transaction.status = "FAILED"
            transactions[index] = _dump(transaction)
            _write(path, transactions)
            charges = _read(directory / "charges.json", [])
            for charge in charges:
                if charge["transaction_id"] == transaction_id:
                    charge["status"] = "FAILED"
            _write(directory / "charges.json", charges)
            return transaction
    raise ValueError("transaction not found")


def create_app(data_dir: Path | None = None) -> FastAPI:
    directory = data_dir or Path(os.environ.get("MINI_PIX_DATA_DIR", DEFAULT_DATA_DIR))
    api = FastAPI(title="Mini Pix")

    @api.post("/charges", response_model=Charge)
    def charges(request: CreateChargeRequest) -> Charge:
        return create_charge(
            request.txid, request.receiver_account_id, request.amount, directory
        )

    @api.post("/resolve", response_model=Charge)
    def resolve(request: ResolveRequest) -> Charge:
        try:
            return resolve_pix_code(request.pix_code, directory)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @api.post("/complete", response_model=Transaction)
    def complete(request: CompleteRequest) -> Transaction:
        try:
            return complete_transaction(
                request.transaction_id,
                directory,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @api.post("/invoices", response_model=Invoice)
    def invoices(request: TransactionRequest) -> Invoice:
        try:
            return generate_invoice(request.transaction_id, directory)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @api.post("/fail", response_model=Transaction)
    def fail(request: TransactionRequest) -> Transaction:
        try:
            return fail_transaction(request.transaction_id, directory)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    return api


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "agent_economy_e2e.mini_pix.app:app", host="127.0.0.1", port=8001, reload=False
    )
