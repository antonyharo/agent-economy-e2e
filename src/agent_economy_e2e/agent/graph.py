from __future__ import annotations

import re
import unicodedata
from typing import Any, Literal, TypedDict, cast

from langchain_core.language_models import BaseChatModel
from langchain_ollama import ChatOllama
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from pydantic import BaseModel, Field

from .mcp import load_mcp_tools


def _plain_text(value: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFD", value.lower())
        if unicodedata.category(character) != "Mn"
    )


def _clean_product_query(query: str) -> str:
    cleaned = re.sub(r"\b(?:tamanho|size)\s+[a-z0-9-]+", "", query, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"^\s*(?:compre|comprar|quero|gostaria\s+de|adicionar)\s+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"^\s*(?:um|uma|o|a)\s+", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def _requested_variant(query: str) -> str | None:
    match = re.search(r"\b(?:tamanho|size)\s+([a-z0-9-]+)", query, flags=re.IGNORECASE)
    return match.group(1).lower() if match else None


class PurchaseRequest(BaseModel):
    product_query: str = Field(description="Product description to search for")
    quantity: int = Field(default=1, ge=1)
    variant_id: str | None = None
    shipping_address: dict[str, str]
    shipping_option: str = "standard"
    payer_account_id: str


class PurchaseState(TypedDict, total=False):
    user_request: str
    product_query: str
    quantity: int
    variant_id: str | None
    shipping_address: dict[str, str]
    shipping_option: str
    payer_account_id: str
    product_id: str
    cart: dict[str, Any]
    totals: dict[str, Any]
    checkout: dict[str, Any]
    instructions: dict[str, Any]
    payment: dict[str, Any]
    order: dict[str, Any]
    status: Literal["running", "awaiting_approval", "cancelled", "completed"]
    error: str


def _nodes(tools: dict[str, Any], model: BaseChatModel) -> dict[str, Any]:
    structured_model = model.with_structured_output(PurchaseRequest)

    async def plan_request(state: PurchaseState) -> dict[str, Any]:
        if "product_query" in state:
            return {}

        user_request = state.get("user_request")
        if user_request is None:
            raise ValueError("O pedido do usuario nao foi informado.")
        request = await structured_model.ainvoke(
            [
                (
                    "system",
                    (
                        "Converta o pedido em dados de compra. "
                        "Nao invente dados ausentes; solicite-os ao usuario."
                    ),
                ),
                ("human", user_request),
            ]
        )
        request = cast(PurchaseRequest, request)
        planned = request.model_dump()
        for field in ("shipping_address", "payer_account_id", "shipping_option"):
            value = state.get(field)
            if value is not None:
                planned[field] = value
        return planned

    async def search_product(state: PurchaseState) -> dict[str, Any]:
        original_query = state.get("product_query")
        if original_query is None:
            raise ValueError("A consulta do produto nao foi informada.")
        query = _clean_product_query(original_query)
        result = await tools["search_products"].ainvoke({"query": query, "limit": 10})
        products = result.get("products", [])
        if not products:
            catalog = await tools["search_products"].ainvoke(
                {"query": "", "limit": 100}
            )
            terms = [term for term in _plain_text(query).split() if len(term) > 1]
            products = [
                product
                for product in catalog.get("products", [])
                if all(
                    term
                    in _plain_text(
                        f"{product.get('name', '')} {product.get('description', '')}"
                    )
                    for term in terms
                )
            ]
        if not products:
            return {"status": "cancelled", "error": "Nenhum produto encontrado."}

        product = products[0]
        variant = _requested_variant(original_query)
        variant_id = state.get("variant_id")
        if variant_id is None and variant is not None:
            matching_variant = next(
                (
                    item
                    for item in product.get("variants", [])
                    if str(item.get("name", "")).lower() == variant
                ),
                None,
            )
            if matching_variant is not None:
                variant_id = matching_variant["id"]
        return {"product_id": product["id"], "variant_id": variant_id}

    async def ensure_cart(state: PurchaseState) -> dict[str, Any]:
        try:
            cart = await tools["get_cart"].ainvoke({})
        except RuntimeError as exc:
            if "No active cart" not in str(exc):
                raise
            cart = await tools["create_cart"].ainvoke({})

        if cart.get("items"):
            cart = await tools["clear_cart"].ainvoke({})
        return {"cart": cart}

    async def add_to_cart(state: PurchaseState) -> dict[str, Any]:
        product_id = state.get("product_id")
        if product_id is None:
            raise ValueError("O produto nao foi identificado.")
        cart = await tools["add_to_cart"].ainvoke(
            {
                "product_id": product_id,
                "quantity": state.get("quantity", 1),
                "variant_id": state.get("variant_id"),
            }
        )
        return {"cart": cart}

    async def calculate_cart(state: PurchaseState) -> dict[str, Any]:
        return {"totals": await tools["calculate_cart"].ainvoke({})}

    async def create_checkout(state: PurchaseState) -> dict[str, Any]:
        cart = state.get("cart")
        shipping_address = state.get("shipping_address")
        if cart is None or shipping_address is None:
            raise ValueError("Carrinho ou endereco de entrega ausente.")
        checkout = await tools["create_checkout"].ainvoke(
            {
                "cart_id": cart["id"],
                "shipping_address": shipping_address,
                "shipping_option": "standard",
                "payment_method": "pix",
            }
        )
        return {"checkout": checkout}

    async def get_payment_instructions(state: PurchaseState) -> dict[str, Any]:
        checkout = state.get("checkout")
        if checkout is None:
            raise ValueError("O checkout nao foi criado.")
        instructions = await tools["get_payment_instructions"].ainvoke(
            {"checkout_id": checkout["checkout_id"]}
        )
        return {"instructions": instructions, "status": "awaiting_approval"}

    def request_approval(state: PurchaseState) -> dict[str, Any]:
        instructions = state.get("instructions")
        checkout = state.get("checkout")
        if instructions is None or checkout is None:
            raise ValueError("As instrucoes de pagamento nao foram geradas.")
        decision = interrupt(
            {
                "type": "payment_approval",
                "checkout_id": checkout["checkout_id"],
                "amount": instructions["amount"],
                "pix_code": instructions["pix_code"],
            }
        )
        if decision is True or decision == {"approved": True}:
            return {"status": "running"}
        return {"status": "cancelled", "error": "Pagamento cancelado pelo usuario."}

    async def authorize_payment(state: PurchaseState) -> dict[str, Any]:
        instructions = state.get("instructions")
        payer_account_id = state.get("payer_account_id")
        checkout = state.get("checkout")
        if instructions is None or payer_account_id is None or checkout is None:
            raise ValueError("Dados insuficientes para autorizar o pagamento.")
        try:
            payment = await tools["authorize_payment"].ainvoke(
                {
                    "payer_account_id": payer_account_id,
                    "pix_code": instructions["pix_code"],
                    "amount": f"{instructions['amount']:.2f}",
                    "reference_id": checkout["checkout_id"],
                }
            )
        except RuntimeError as exc:
            return {"status": "cancelled", "error": str(exc)}
        return {"payment": payment}

    async def confirm_order(state: PurchaseState) -> dict[str, Any]:
        checkout = state.get("checkout")
        instructions = state.get("instructions")
        if checkout is None or instructions is None:
            raise ValueError("Dados insuficientes para confirmar o pedido.")
        order = await tools["confirm_order"].ainvoke(
            {
                "checkout_id": checkout["checkout_id"],
                "payment_id": instructions["payment_id"],
            }
        )
        return {"order": order, "status": "completed"}

    return locals()


def _after_search(state: PurchaseState) -> str:
    return END if state.get("status") == "cancelled" else "create_cart"


def _after_approval(state: PurchaseState) -> str:
    return END if state.get("status") == "cancelled" else "authorize_payment"


def _after_authorize_payment(state: PurchaseState) -> str:
    return END if state.get("status") == "cancelled" else "confirm_order"


def build_purchase_graph(
    model: BaseChatModel | None = None, tools: dict[str, Any] | None = None
):
    """Build the purchase graph. HTTP Mini Bank/Pix must already be running."""
    if tools is None:
        raise ValueError("As tools MCP devem ser fornecidas.")
    resolved_model = model or ChatOllama(model="qwen3:1.7b", temperature=0)
    graph = StateGraph(PurchaseState)
    nodes = _nodes(tools, resolved_model)

    for name in (
        "plan_request",
        "search_product",
        "ensure_cart",
        "add_to_cart",
        "calculate_cart",
        "create_checkout",
        "get_payment_instructions",
        "request_approval",
        "authorize_payment",
        "confirm_order",
    ):
        graph.add_node(name, nodes[name])

    graph.add_edge(START, "plan_request")
    graph.add_edge("plan_request", "search_product")
    graph.add_conditional_edges(
        "search_product", _after_search, {"create_cart": "ensure_cart", END: END}
    )
    graph.add_edge("ensure_cart", "add_to_cart")
    graph.add_edge("add_to_cart", "calculate_cart")
    graph.add_edge("calculate_cart", "create_checkout")
    graph.add_edge("create_checkout", "get_payment_instructions")
    graph.add_edge("get_payment_instructions", "request_approval")
    graph.add_conditional_edges(
        "request_approval",
        _after_approval,
        {"authorize_payment": "authorize_payment", END: END},
    )
    graph.add_conditional_edges(
        "authorize_payment",
        _after_authorize_payment,
        {"confirm_order": "confirm_order", END: END},
    )
    graph.add_edge("confirm_order", END)
    return graph.compile(checkpointer=MemorySaver())


async def build_graph(model: BaseChatModel | None = None):
    tools = await load_mcp_tools()
    return build_purchase_graph(model=model, tools=tools)
