from __future__ import annotations

import json
import os
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import FastAPI, HTTPException

from .models import Account, AccountOperation, BalanceResponse, PixPayment

DEFAULT_DATA_DIR = Path(__file__).parent / "data"
DEFAULT_PIX_URL = "http://127.0.0.1:8001"


def _read_accounts(path: Path) -> list[dict[str, Any]]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(
            json.dumps(
                [
                    {"account_id": "buyer", "balance": "100.00", "currency": "BRL"},
                    {"account_id": "seller", "balance": "50.00", "currency": "BRL"},
                ],
                indent=2,
            ),
            encoding="utf-8",
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _write_accounts(path: Path, records: list[dict[str, Any]]) -> None:
    def encode(value: Any) -> str:
        if isinstance(value, Decimal):
            return format(value, ".2f")
        raise TypeError

    path.write_text(json.dumps(records, indent=2, default=encode), encoding="utf-8")


def _account(records: list[dict[str, Any]], account_id: str) -> tuple[int, Account]:
    for index, record in enumerate(records):
        if record["account_id"] == account_id:
            return index, Account.model_validate(record)
    raise ValueError("account not found")


def _operation(
    account_id: str,
    amount: Decimal,
    transaction_id: str,
    data_dir: Path | None,
    direction: str,
) -> Account:
    path = (data_dir or DEFAULT_DATA_DIR) / "accounts.json"
    records = _read_accounts(path)
    index, account = _account(records, account_id)
    metadata = records[index]
    transaction_key = f"_{direction}_transactions"
    transactions = metadata.setdefault(transaction_key, [])
    if transaction_id in transactions:
        return account
    if direction == "debit" and account.balance < amount:
        raise ValueError("insufficient balance")
    new_balance = (
        account.balance - amount if direction == "debit" else account.balance + amount
    )
    if new_balance < 0:
        raise ValueError("balance cannot be negative")
    metadata["balance"] = new_balance
    transactions.append(transaction_id)
    records[index] = metadata
    _write_accounts(path, records)
    return Account.model_validate(metadata)


def check_balance(account_id: str, data_dir: Path | None = None) -> Account:
    records = _read_accounts((data_dir or DEFAULT_DATA_DIR) / "accounts.json")
    return _account(records, account_id)[1]


def debit_account(
    account_id: str,
    amount: Decimal,
    transaction_id: str,
    data_dir: Path | None = None,
) -> Account:
    return _operation(account_id, amount, transaction_id, data_dir, "debit")


def credit_account(
    account_id: str,
    amount: Decimal,
    transaction_id: str,
    data_dir: Path | None = None,
) -> Account:
    return _operation(account_id, amount, transaction_id, data_dir, "credit")


def _rollback_operation(
    account_id: str,
    amount: Decimal,
    transaction_id: str,
    data_dir: Path | None,
    direction: str,
    increase: bool,
) -> None:
    path = (data_dir or DEFAULT_DATA_DIR) / "accounts.json"
    records = _read_accounts(path)
    index, account = _account(records, account_id)
    balance = account.balance + amount if increase else account.balance - amount
    if balance < 0:
        raise ValueError("balance cannot be negative")
    records[index].setdefault(f"_{direction}_transactions", []).remove(transaction_id)
    records[index]["balance"] = balance
    _write_accounts(path, records)


def _pix_request(base_url: str, endpoint: str, body: dict[str, Any]) -> dict[str, Any]:
    payload = json.dumps(body, default=str).encode("utf-8")
    request = Request(
        f"{base_url.rstrip('/')}{endpoint}",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError) as exc:
        raise ValueError(f"Mini Pix request failed: {exc}") from exc


def pay_pix(
    pix_code: str,
    payer_account_id: str,
    amount: Decimal,
    data_dir: Path | None = None,
    pix_url: str | None = None,
) -> dict[str, Any]:
    directory = data_dir or DEFAULT_DATA_DIR
    base_url = pix_url or os.environ.get("MINI_PIX_URL", DEFAULT_PIX_URL)
    charge = _pix_request(base_url, "/resolve", {"pix_code": pix_code})
    charge_amount = Decimal(charge["amount"])
    if charge_amount != amount:
        raise ValueError("amount does not match charge")
    txid = charge["transaction_id"]
    if charge["status"] == "COMPLETED":
        return _pix_request(base_url, "/invoices", {"transaction_id": txid})
    receiver = charge["receiver_account_id"]
    debit_done = False
    credit_done = False
    try:
        check_balance(payer_account_id, directory)
        debit_account(payer_account_id, amount, txid, directory)
        debit_done = True
        credit_account(receiver, amount, txid, directory)
        credit_done = True
        _pix_request(
            base_url,
            "/complete",
            {"transaction_id": txid},
        )
        return _pix_request(base_url, "/invoices", {"transaction_id": txid})
    except ValueError:
        if credit_done:
            _rollback_operation(
                receiver, amount, txid, directory, "credit", increase=False
            )
        if debit_done:
            _rollback_operation(
                payer_account_id, amount, txid, directory, "debit", increase=True
            )
        try:
            _pix_request(base_url, "/fail", {"transaction_id": txid})
        except ValueError:
            pass
        raise


def create_app(data_dir: Path | None = None, pix_url: str | None = None) -> FastAPI:
    directory = data_dir or Path(os.environ.get("MINI_BANK_DATA_DIR", DEFAULT_DATA_DIR))
    api = FastAPI(title="Mini Bank")

    @api.get("/accounts/{account_id}/balance", response_model=BalanceResponse)
    def balance(account_id: str) -> Account:
        try:
            return check_balance(account_id, directory)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @api.post("/accounts/debit", response_model=Account)
    def debit(request: AccountOperation) -> Account:
        try:
            return debit_account(
                request.account_id, request.amount, request.transaction_id, directory
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @api.post("/accounts/credit", response_model=Account)
    def credit(request: AccountOperation) -> Account:
        try:
            return credit_account(
                request.account_id, request.amount, request.transaction_id, directory
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @api.post("/payments/pix")
    def payment(request: PixPayment) -> dict[str, Any]:
        try:
            return pay_pix(
                request.pix_code,
                request.payer_account_id,
                request.amount,
                directory,
                pix_url,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    return api


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "agent_economy_e2e.mini_bank.app:app", host="127.0.0.1", port=8000, reload=False
    )
