import asyncio
from typing import Any

from agent_economy_e2e.agent import cli
from agent_economy_e2e.agent.graph import (
    _after_authorize_payment,
    _clean_product_query,
    _fallback_purchase_items,
    _nodes,
    _requested_quantity,
    _search_terms,
)


class FakeModel:
    def with_structured_output(self, model: Any) -> "FakeModel":
        return self


class PlannedModel:
    def with_structured_output(self, model: Any) -> "PlannedModel":
        return self

    async def ainvoke(self, messages: Any) -> Any:
        return type(
            "PlannedRequest",
            (),
            {
                "model_dump": lambda self: {
                    "items": [
                        {"product_query": "mochila urban", "quantity": 2, "variant_id": None},
                        {"product_query": "tenis x", "quantity": 2, "variant_id": None},
                    ],
                    "product_query": "",
                    "quantity": 1,
                    "variant_id": None,
                    "shipping_address": {},
                    "shipping_option": "standard",
                    "payer_account_id": "",
                }
            },
        )()


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


def test_product_query_removes_purchase_details_before_catalog_search() -> None:
    assert _clean_product_query("Compre dois Tenis X tamanho 42") == "Tenis X"
    assert _clean_product_query("Compre duas mochilas urban") == "mochilas urban"
    assert _search_terms("mochilas urban") == {"mochila", "urban"}
    assert _requested_quantity("Compre quatro Tenis X tamanho 42") == 4
    assert _requested_quantity("Compre Tenis X tamanho 42") is None
    assert _fallback_purchase_items("quero comprar 2 mochilas urban e 2 tenis x") == [
        {"product_query": "mochilas urban", "quantity": 2, "variant_id": None},
        {"product_query": "tenis x", "quantity": 2, "variant_id": None},
    ]


def test_plan_request_preserves_multiple_products() -> None:
    nodes = _nodes({}, PlannedModel())

    result = asyncio.run(
        nodes["plan_request"](
            {
                "user_request": "quero comprar 2 mochilas urban e 2 tenis x",
                "shipping_address": {},
                "payer_account_id": "buyer",
            }
        )
    )

    assert result["items"] == [
        {"product_query": "mochilas urban", "quantity": 2, "variant_id": None},
        {"product_query": "tenis x", "quantity": 2, "variant_id": None},
    ]


def test_add_to_cart_adds_each_planned_product() -> None:
    add_to_cart = ReturningTool({"id": "cart-123", "items": []})
    nodes = _nodes({"add_to_cart": add_to_cart}, FakeModel())

    result = asyncio.run(
        nodes["add_to_cart"](
            {
                "resolved_items": [
                    {"product_id": "prod_mochila_urban", "quantity": 2, "variant_id": None},
                    {"product_id": "prod_tenis_x", "quantity": 2, "variant_id": None},
                ]
            }
        )
    )

    assert result["cart"]["id"] == "cart-123"
    assert add_to_cart.calls == 2


def test_public_payment_messages_are_compact() -> None:
    approval = cli._approval_message(
        {
            "checkout_id": "chk-123",
            "items": [{"name": "Tenis X", "quantity": 1, "unit_price": 799.9}],
            "amount": 819.9,
            "payment_method": "pix",
            "pix_code": "PIX-123",
        }
    )
    assert approval == {
        "type": "payment_approval",
        "items": [{"name": "Tenis X", "quantity": 1, "unit_price": 799.9}],
        "total": 819.9,
        "payment_method": "pix",
        "pix_code": "PIX-123",
    }

    assert cli._public_result(
        {
            "status": "completed",
            "cart": {"id": "cart-123"},
            "payment": {"status": "COMPLETED"},
            "order": {
                "order_id": "ord-123",
                "status": "confirmed",
                "shipping_address": {"city": "Sao Paulo"},
            },
        }
    ) == {
        "order": {
            "order_id": "ord-123",
            "status": "confirmed",
            "shipping_address": {"city": "Sao Paulo"},
        }
    }


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
