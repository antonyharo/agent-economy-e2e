import asyncio
from typing import Any

from agent_economy_e2e.agent import cli
from agent_economy_e2e.agent.graph import _after_authorize_payment, _nodes


class FakeModel:
    def with_structured_output(self, model: Any) -> "FakeModel":
        return self


class FailingPaymentTool:
    async def ainvoke(self, arguments: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError(
            "Error executing tool authorize_payment: Compra recusada: saldo insuficiente"
        )


class FailingGraph:
    async def ainvoke(self, input_value: Any, config: Any) -> dict[str, Any]:
        raise RuntimeError("falha inesperada")


def test_authorize_payment_returns_structured_business_error() -> None:
    nodes = _nodes(
        {"authorize_payment": FailingPaymentTool()},
        FakeModel(),
    )
    state = {
        "instructions": {"pix_code": "PIX-123", "amount": 819.9},
        "payer_account_id": "buyer",
        "checkout": {"checkout_id": "chk-123"},
    }

    result = asyncio.run(nodes["authorize_payment"](state))

    assert result == {
        "status": "cancelled",
        "error": (
            "Error executing tool authorize_payment: "
            "Compra recusada: saldo insuficiente"
        ),
    }
    assert _after_authorize_payment(result) == "__end__"


def test_run_returns_structured_unexpected_error(monkeypatch) -> None:
    async def fake_build_graph():
        return FailingGraph()

    async def fake_close_mcp_tools():
        return None

    monkeypatch.setattr(cli, "build_graph", fake_build_graph)
    monkeypatch.setattr(cli, "close_mcp_tools", fake_close_mcp_tools)

    result = asyncio.run(cli.run("Compre um Tenis X", "buyer", {}))

    assert result == {
        "status": "error",
        "error": {"type": "RuntimeError", "message": "falha inesperada"},
    }
