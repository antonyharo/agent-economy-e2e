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


async def run(
    request: str, payer_account_id: str, address: dict[str, str]
) -> dict[str, Any]:
    try:
        graph = await build_graph()
        config: RunnableConfig = {"configurable": {"thread_id": "local-purchase"}}
        state: PurchaseState = {
            "user_request": request,
            "payer_account_id": payer_account_id,
            "shipping_address": address,
            "status": "running",
        }

        result = await graph.ainvoke(state, config)
        while result.get("__interrupt__"):
            interruption = result["__interrupt__"][0]
            print(json.dumps(interruption.value, ensure_ascii=False, indent=2))
            approved = input("Autorizar pagamento? [s/N] ").strip().lower() == "s"
            result = await graph.ainvoke(Command(resume=approved), config)
        return result
    except Exception as exc:
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
    parser.add_argument(
        "--address", type=json.loads, default=json.dumps(DEFAULT_ADDRESS)
    )
    args = parser.parse_args()

    result = asyncio.run(run(args.request, args.payer_account_id, args.address))
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
