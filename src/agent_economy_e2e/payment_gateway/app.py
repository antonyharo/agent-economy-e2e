from __future__ import annotations

import json
import os
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .models import AuthorizePaymentRequest

DEFAULT_BANK_URL = "http://127.0.0.1:8000"
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data" / "payment-gateway"


def _read_agents(data_dir: Path | None = None) -> list[dict[str, Any]]:
    path = (
        data_dir or Path(os.environ.get("PAYMENT_GATEWAY_DATA_DIR", DEFAULT_DATA_DIR))
    ) / "agents.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(
            json.dumps(
                [
                    {
                        "agent_id": "default",
                        "account_id": "buyer",
                        "max_expeding_value": "1000.00",
                        "permited_categories": ["acessorios", "calcados", "roupas"],
                        "require_human_approval": False,
                        "human_approval_threshold": None,
                    }
                ],
                indent=2,
            ),
            encoding="utf-8",
        )
    records = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise ValueError("invalid agent registry")
    return records


def _validate_policy(
    agent_id: str,
    payer_account_id: str,
    amount: Decimal,
    categories: list[str],
    data_dir: Path | None = None,
    human_approved: bool = False,
) -> dict[str, Any]:
    agent = next(
        (item for item in _read_agents(data_dir) if item.get("agent_id") == agent_id),
        None,
    )
    if agent is None:
        raise ValueError("pagamento negado: agente nao cadastrado")
    if agent.get("account_id") != payer_account_id:
        raise ValueError("pagamento negado: agente nao vinculado a conta")
    try:
        maximum = Decimal(str(agent["max_expeding_value"]))
    except (KeyError, ArithmeticError, ValueError) as exc:
        raise ValueError("pagamento negado: limite do agente invalido") from exc
    permitted = {
        str(category).lower() for category in agent.get("permited_categories", [])
    }
    denied = [category for category in categories if category.lower() not in permitted]
    if denied:
        raise ValueError(
            f"pagamento negado: categoria nao permitida ({', '.join(denied)})"
        )
    threshold_value = agent.get("human_approval_threshold")
    always_requires_human = bool(agent.get("require_human_approval", False))
    if isinstance(threshold_value, bool):
        if not threshold_value:
            raise ValueError("pagamento negado: pre-aprovacao humana desabilitada")
        always_requires_human = True
        threshold_value = None
    requires_human_approval = always_requires_human
    if threshold_value is not None:
        try:
            requires_human_approval = requires_human_approval or amount > Decimal(
                str(threshold_value)
            )
        except (ArithmeticError, ValueError) as exc:
            raise ValueError(
                "pagamento negado: limite de pre-aprovacao invalido"
            ) from exc
    over_limit = amount > maximum
    if over_limit and not requires_human_approval:
        raise ValueError(f"pagamento negado: valor excede o limite de {maximum:.2f}")
    if over_limit and not human_approved:
        requires_human_approval = True
        reason = f"valor excede o limite de {maximum:.2f}; aprovacao humana necessaria"
    elif requires_human_approval:
        reason = "pre-aprovacao humana obrigatoria"
    else:
        reason = "pre-aprovacao humana nao necessaria"
    return {
        "agent_id": agent_id,
        "approved": True,
        "requires_human_approval": requires_human_approval,
        "reason": reason,
    }


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
    agent_id: str = "default",
    categories: list[str] | None = None,
    category: str | None = None,
    data_dir: Path | None = None,
    human_approved: bool = False,
) -> dict[str, Any]:
    requested_categories = list(categories or [])
    if category is not None:
        requested_categories.append(category)
    request = AuthorizePaymentRequest(
        agent_id=agent_id,
        payer_account_id=payer_account_id,
        pix_code=pix_code,
        amount=amount,
        reference_id=reference_id,
        category=category,
        categories=requested_categories,
        human_approved=human_approved,
    )
    policy = _validate_policy(
        request.agent_id,
        request.payer_account_id,
        request.amount,
        request.categories,
        data_dir,
        request.human_approved,
    )
    if policy["requires_human_approval"] and not request.human_approved:
        raise ValueError("pagamento pendente: pre-aprovacao humana necessaria")
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
            return {
                **json.loads(response.read().decode("utf-8")),
                "approved": True,
                "reason": "pagamento aprovado",
            }
    except HTTPError as exc:
        detail = _error_detail(exc)
        if exc.code == 409:
            raise ValueError(f"Compra recusada: {_decline_reason(detail)}") from exc
        raise ValueError(f"Falha no Mini Bank (HTTP {exc.code}): {detail}") from exc
    except (URLError, TimeoutError) as exc:
        raise ValueError(f"Mini Bank request failed: {exc}") from exc


def evaluate_payment(
    payer_account_id: str,
    amount: Decimal,
    agent_id: str = "default",
    categories: list[str] | None = None,
    category: str | None = None,
    data_dir: Path | None = None,
) -> dict[str, Any]:
    requested_categories = list(categories or [])
    if category is not None:
        requested_categories.append(category)
    return _validate_policy(
        agent_id,
        payer_account_id,
        amount.quantize(Decimal("0.01")),
        requested_categories,
        data_dir,
    )
