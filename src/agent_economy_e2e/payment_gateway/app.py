from __future__ import annotations

import json
import os
from decimal import Decimal
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .models import AuthorizePaymentRequest

DEFAULT_BANK_URL = "http://127.0.0.1:8000"


def _error_detail(error: HTTPError) -> str:
    try:
        payload = json.loads(error.read().decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        return error.reason or "erro desconhecido"
    detail = payload.get("detail") if isinstance(payload, dict) else None
    return str(detail or error.reason or "erro desconhecido")


def _decline_reason(detail: str) -> str:
    if detail == "insufficient balance":
        return "saldo insuficiente"
    return detail


def authorize_payment(
    payer_account_id: str,
    pix_code: str,
    amount: Decimal,
    reference_id: str,
    bank_url: str | None = None,
) -> dict[str, Any]:
    request = AuthorizePaymentRequest(
        payer_account_id=payer_account_id,
        pix_code=pix_code,
        amount=amount,
        reference_id=reference_id,
    )
    payload = {
        "pix_code": request.pix_code,
        "payer_account_id": request.payer_account_id,
        "amount": str(request.amount),
    }
    url = bank_url or os.environ.get("MINI_BANK_URL", DEFAULT_BANK_URL)
    http_request = Request(
        f"{url.rstrip('/')}/payments/pix",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(http_request, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = _error_detail(exc)
        if exc.code == 409:
            raise ValueError(f"Compra recusada: {_decline_reason(detail)}") from exc
        raise ValueError(f"Falha no Mini Bank (HTTP {exc.code}): {detail}") from exc
    except (URLError, TimeoutError) as exc:
        raise ValueError(f"Mini Bank request failed: {exc}") from exc
