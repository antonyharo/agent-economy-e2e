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


class ReturningTool:
    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result
        self.calls = 0

    async def ainvoke(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.calls += 1
        return self.result


class MissingCartTool:
    def __init__(self) -> None:
        self.calls = 0

    async def ainvoke(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.calls += 1
        raise RuntimeError("Error executing tool get_cart: No active cart")


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


def test_ensure_cart_reuses_existing_cart() -> None:
    get_cart = ReturningTool({"id": "cart-existing"})
    create_cart = ReturningTool({"id": "cart-created"})
    nodes = _nodes(
        {"get_cart": get_cart, "create_cart": create_cart},
        FakeModel(),
    )

    result = asyncio.run(nodes["ensure_cart"]({}))

    assert result == {"cart": {"id": "cart-existing"}}
    assert get_cart.calls == 1
    assert create_cart.calls == 0


def test_ensure_cart_creates_cart_when_none_is_active() -> None:
    get_cart = MissingCartTool()
    create_cart = ReturningTool({"id": "cart-created"})
    nodes = _nodes(
        {"get_cart": get_cart, "create_cart": create_cart},
        FakeModel(),
    )

    result = asyncio.run(nodes["ensure_cart"]({}))

    assert result == {"cart": {"id": "cart-created"}}
    assert get_cart.calls == 1
    assert create_cart.calls == 1


def test_ensure_cart_can_clear_existing_items() -> None:
    get_cart = ReturningTool(
        {
            "id": "cart-existing",
            "items": [{"product_id": "prod_tenis_x", "quantity": 1}],
        }
    )
    clear_cart = ReturningTool({"id": "cart-existing", "items": []})
    nodes = _nodes(
        {"get_cart": get_cart, "clear_cart": clear_cart},
        FakeModel(),
    )

    result = asyncio.run(nodes["ensure_cart"]({}))

    assert result == {"cart": {"id": "cart-existing", "items": []}}
    assert clear_cart.calls == 1


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
