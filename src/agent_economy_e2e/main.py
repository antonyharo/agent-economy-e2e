from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from rich.console import Console
from rich.json import JSON
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from .agent import PurchaseState, agent
from .agent.mcp import MCPObserver, close_mcp_tools, load_mcp_tools

DEFAULT_ADDRESS = {
    "street": "Rua das Flores",
    "number": "123",
    "city": "Sao Paulo",
    "state": "SP",
    "postal_code": "01000-000",
    "country": "BR",
}


class DemoUI:
    """Compact terminal presentation for the end-to-end demonstration."""

    def __init__(self) -> None:
        self.console = Console()

    @staticmethod
    def _money(value: Any) -> str:
        if value is None:
            return "n/d"
        return (
            f"R$ {float(value):,.2f}".replace(",", "X")
            .replace(".", ",")
            .replace("X", ".")
        )

    @staticmethod
    def _address(value: dict[str, Any]) -> str:
        return ", ".join(
            str(value.get(field, ""))
            for field in ("street", "number", "city", "state", "postal_code")
            if value.get(field)
        )

    def header(self, request: str) -> None:
        self.console.print(
            Panel(
                f"[bold]Pedido:[/bold] {request}",
                title="[bold cyan]Agent Economy Sandbox[/bold cyan]",
                border_style="cyan",
                padding=(0, 1),
            )
        )

    def chat(self, message: str, title: str = "Agente") -> None:
        self.console.print(
            Panel(
                message, title=f"[bold green]{title}[/bold green]", border_style="green"
            )
        )

    def mcp_event(
        self,
        phase: str,
        tool: str,
        arguments: dict[str, Any],
        result: dict[str, Any] | None,
        error: Exception | None,
    ) -> None:
        if phase == "start":
            messages = {
                "evaluate_payment": "Gateway analisando as regras de pagamento...",
                "authorize_payment": "Gateway autorizando e debitando o pagamento...",
                "confirm_order": "Ecommerce confirmando o pedido...",
            }
            if tool in messages:
                self.console.print(f"[yellow]•[/yellow] {messages[tool]}")
            return
        if phase == "error":
            self.console.print(f"[red]✗[/red] {tool}: {error}")
            return
        if result is None:
            return

        if tool == "search_products":
            products = result.get("products", [])
            if products:
                product = products[0]
                self.console.print(
                    f"[cyan]•[/cyan] Agente escolheu [bold]{product.get('name', 'produto')}[/bold] "
                    f"({self._money(product.get('price'))})."
                )
        elif tool == "create_cart":
            self.console.print("[cyan]•[/cyan] Carrinho criado para a compra.")
        elif tool == "add_to_cart":
            self.console.print(
                f"[cyan]•[/cyan] Produto adicionado ao carrinho: quantidade [bold]{arguments.get('quantity', 1)}[/bold]."
            )
        elif tool == "calculate_cart":
            self.console.print(
                f"[cyan]•[/cyan] Carrinho calculado: subtotal {self._money(result.get('subtotal'))}, "
                f"frete {self._money(result.get('shipping'))}, total [bold]{self._money(result.get('total'))}[/bold]."
            )
        elif tool == "create_checkout":
            self.console.print(
                f"[cyan]•[/cyan] Checkout criado para [bold]{self._address(arguments.get('shipping_address', {}))}[/bold]. "
                f"Total {self._money(result.get('total'))}."
            )
        elif tool == "get_payment_instructions":
            self.console.print(
                f"[cyan]•[/cyan] Mini Pix gerou a cobrança de [bold]{self._money(result.get('amount'))}[/bold]."
            )
        elif tool == "evaluate_payment":
            if result.get("requires_human_approval"):
                self.console.print(
                    "[yellow]•[/yellow] Gateway solicitou aprovação humana."
                )
            else:
                self.console.print(
                    "[green]•[/green] Gateway aprovou automaticamente a política."
                )
        elif tool == "authorize_payment":
            self.console.print(
                f"[green]✓[/green] Mini Bank debitou [bold]{self._money(result.get('amount'))}[/bold]; "
                "Mini Pix aceitou a transação."
            )
        elif tool == "confirm_order":
            self.console.print(
                f"[green]✓[/green] Pedido confirmado: [bold]{result.get('order_id', 'sem id')}[/bold]."
            )


async def build_graph(observer: MCPObserver | None = None):
    """Initialize MCPs and configure the purchase agent."""
    tools = await load_mcp_tools(observer)
    return agent(tools=tools)


def _approval_message(interruption: dict[str, Any]) -> dict[str, Any]:
    checkout = interruption.get("checkout", {})
    return {
        "items": [
            {
                "name": item.get("name"),
                "quantity": item.get("quantity"),
                "unit_price": item.get("unit_price"),
            }
            for item in interruption.get("items", [])
        ],
        "subtotal": checkout.get("subtotal"),
        "shipping": checkout.get("shipping"),
        "discount": checkout.get("discount"),
        "total": checkout.get("total", interruption["amount"]),
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
    ui = DemoUI()
    ui.header(request)
    try:
        graph = await build_graph(ui.mcp_event)
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
            approval = _approval_message(interruption.value)
            items = ", ".join(
                f"{item['name']} x{item['quantity']}" for item in approval["items"]
            )
            ui.chat(
                f"O gateway pediu sua aprovação para [bold]{items}[/bold].\n"
                f"Total: [bold]{ui._money(approval['total'])}[/bold]",
                title="Aprovação necessária",
            )
            reason = interruption.value.get("reason", "")
            if reason:
                ui.console.print(f"[dim]Motivo: {reason}[/dim]")
            decision = (
                Prompt.ask(
                    "Deseja aprovar este pagamento?", choices=["s", "n"], default="n"
                )
                == "s"
            )
            result = await graph.ainvoke(Command(resume=decision), config)
        if result.get("payment"):
            payment = result["payment"]
            ui.chat(
                f"Pagamento concluído de [bold]{ui._money(payment.get('amount'))}[/bold].\n"
                f"Transação: {payment.get('transaction_id', 'n/d')}",
                title="Agente",
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
    ui = DemoUI()
    ui.console.print(
        Panel(JSON.from_data(result), title="Resultado", border_style="cyan")
    )


if __name__ == "__main__":
    main()
