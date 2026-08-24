from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from .graph import PurchaseState, build_graph
from .mcp import close_mcp_tools

DEFAULT_ADDRESS = {
    "street": "Rua das Flores",
    "number": "123",
    "city": "Sao Paulo",
    "state": "SP",
    "postal_code": "01000-000",
    "country": "BR",
}


def _approval_message(interruption: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "payment_approval",
        "items": [
            {
                "name": item.get("name"),
                "quantity": item.get("quantity"),
                "unit_price": item.get("unit_price"),
            }
            for item in interruption.get("items", [])
        ],
        "total": interruption["amount"],
        "payment_method": interruption["payment_method"],
        "pix_code": interruption["pix_code"],
    }


def _payment_success_message(payment: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "payment_success",
        "receipt": {
            "invoice_id": payment.get("invoice_id"),
            "transaction_id": payment.get("transaction_id"),
        },
        "amount": payment.get("amount"),
        "currency": payment.get("currency"),
        "status": payment.get("status"),
    }


def _public_result(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("status") == "completed":
        return {"order": result["order"]}
    return {key: result[key] for key in ("status", "error") if key in result}


async def run(
    request: str,
    payer_account_id: str,
    address: dict[str, str],
    agent_id: str = "default",
) -> dict[str, Any]:
    try:
        graph = await build_graph()
        config: RunnableConfig = {"configurable": {"thread_id": "local-purchase"}}
        state: PurchaseState = {
            "user_request": request,
            "payer_account_id": payer_account_id,
            "agent_id": agent_id,
            "shipping_address": address,
            "status": "running",
        }

        result = await graph.ainvoke(state, config)
        while result.get("__interrupt__"):
            interruption = result["__interrupt__"][0]
            print(
                json.dumps(
                    _approval_message(interruption.value),
                    ensure_ascii=False,
                    indent=2,
                )
            )
            decision = input("Autorizar pagamento? [s/N] ").strip().lower() == "s"
            result = await graph.ainvoke(Command(resume=decision), config)
        if result.get("payment"):
            print(
                json.dumps(
                    _payment_success_message(result["payment"]),
                    ensure_ascii=False,
                    indent=2,
                )
            )
        return _public_result(result)
    except (EOFError, OSError, RuntimeError, ValueError) as exc:
        return {
            "status": "error",
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
            },
        }
    finally:
        await close_mcp_tools()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Executa o agente de compras LangGraph."
    )
    parser.add_argument("request", help="Pedido de compra em linguagem natural.")
    parser.add_argument("--payer-account-id", default="buyer")
    parser.add_argument("--agent-id", default="default")
    parser.add_argument(
        "--address", type=json.loads, default=json.dumps(DEFAULT_ADDRESS)
    )
    args = parser.parse_args()

    result = asyncio.run(
        run(args.request, args.payer_account_id, args.address, args.agent_id)
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
