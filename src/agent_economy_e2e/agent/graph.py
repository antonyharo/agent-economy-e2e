from __future__ import annotations

import os
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


def _search_terms(value: str) -> set[str]:
    terms = set(re.findall(r"[a-z0-9]+", _plain_text(value)))
    return {
        term[:-1] if len(term) > 3 and term.endswith("s") else term for term in terms
    }


def _clean_product_query(query: str) -> str:
    cleaned = re.sub(r"\b(?:tamanho|size)\s+[a-z0-9-]+", "", query, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"^\s*(?:compre|comprar|quero|gostaria\s+de|adicionar)\s+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"^\s*(?:um|uma|dois|duas|tres|três|quatro|cinco|o|a)\s+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    return cleaned.strip()


def _requested_quantity(query: str) -> int | None:
    quantities = {
        "um": 1,
        "uma": 1,
        "dois": 2,
        "duas": 2,
        "tres": 3,
        "três": 3,
        "quatro": 4,
        "cinco": 5,
    }
    match = re.search(
        r"^\s*(?:compre|quero\s+comprar|comprar|quero|gostaria\s+de|adicionar)?\s*"
        r"(\d+|um|uma|dois|duas|tres|três|quatro|cinco)\b",
        query,
        flags=re.IGNORECASE,
    )
    if match is None:
        return None
    value = match.group(1).lower()
    return int(value) if value.isdigit() else quantities[value]


def _fallback_purchase_items(request: str) -> list[dict[str, Any]]:
    parts = re.split(r"\s+(?:e|,)\s+", request, flags=re.IGNORECASE)
    if len(parts) == 1:
        return []
    items = []
    for part in parts:
        quantity = _requested_quantity(part) or 1
        query = re.sub(
            r"^\s*(?:compre|comprar|quero\s+comprar|quero|gostaria\s+de|adicionar)\s+",
            "",
            part,
            flags=re.IGNORECASE,
        )
        query = re.sub(
            r"^\s*(?:\d+|um|uma|dois|duas|tres|três|quatro|cinco)\b\s*",
            "",
            query,
            flags=re.IGNORECASE,
        ).strip()
        if query:
            items.append(
                {"product_query": query, "quantity": quantity, "variant_id": None}
            )
    return items


def _requested_variant(query: str) -> str | None:
    match = re.search(r"\b(?:tamanho|size)\s+([a-z0-9-]+)", query, flags=re.IGNORECASE)
    return match.group(1).lower() if match else None


class PurchaseItem(BaseModel):
    product_query: str = Field(description="Product name or description")
    quantity: int = Field(default=1, ge=1)
    variant_id: str | None = None


class PurchaseRequest(BaseModel):
    items: list[PurchaseItem] = Field(
        default_factory=list,
        description="Every product requested by the user, with its quantity",
    )
    product_query: str = ""
    quantity: int = Field(default=1, ge=1)
    variant_id: str | None = None
    shipping_address: dict[str, str] = Field(default_factory=dict)
    shipping_option: str = "standard"
    payer_account_id: str = ""
    agent_id: str = "default"


class PurchaseState(TypedDict, total=False):
    user_request: str
    product_query: str
    quantity: int
    variant_id: str | None
    shipping_address: dict[str, str]
    shipping_option: str
    payer_account_id: str
    agent_id: str
    items: list[dict[str, Any]]
    resolved_items: list[dict[str, Any]]
    product_id: str
    cart: dict[str, Any]
    totals: dict[str, Any]
    checkout: dict[str, Any]
    instructions: dict[str, Any]
    payment_policy: dict[str, Any]
    human_approved: bool
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
                        "Converta o pedido em dados de compra. Gere um item para cada produto. "
                        "A lista items deve conter todos os produtos pedidos, "
                        "product_query deve conter somente o nome ou descricao do produto, "
                        "sem verbos de compra, quantidade ou tamanho. "
                        "Converta quantidades escritas por extenso para numero em quantity. "
                        "Extraia o tamanho para variant_id quando ele existir; use null quando ausente. "
                        "Nao invente dados ausentes; solicite-os ao usuario."
                    ),
                ),
                ("human", user_request),
            ]
        )
        request = cast(PurchaseRequest, request)
        planned = request.model_dump()
        fallback_items = _fallback_purchase_items(user_request)
        if fallback_items:
            planned["items"] = fallback_items
        if not planned["items"] and planned["product_query"]:
            planned["items"] = [
                {
                    "product_query": planned["product_query"],
                    "quantity": planned["quantity"],
                    "variant_id": planned["variant_id"],
                }
            ]
        requested_quantity = _requested_quantity(user_request)
        if requested_quantity is not None and len(planned["items"]) == 1:
            planned["items"][0]["quantity"] = requested_quantity
        if not planned["items"]:
            raise ValueError("Nenhum produto foi identificado no pedido.")
        planned["product_query"] = planned["items"][0]["product_query"]
        planned["quantity"] = planned["items"][0]["quantity"]
        planned["variant_id"] = planned["items"][0]["variant_id"]
        for field in (
            "shipping_address",
            "payer_account_id",
            "agent_id",
            "shipping_option",
        ):
            value = state.get(field)
            if value is not None:
                planned[field] = value
        return planned

    async def search_product(state: PurchaseState) -> dict[str, Any]:
        requested_items = state.get("items", [])
        if not requested_items:
            original_query = state.get("product_query")
            if original_query is None:
                raise ValueError("A consulta do produto nao foi informada.")
            requested_items = [
                {
                    "product_query": original_query,
                    "quantity": state.get("quantity", 1),
                    "variant_id": state.get("variant_id"),
                }
            ]

        resolved_items = []
        for requested in requested_items:
            original_query = requested["product_query"]
            query = _clean_product_query(original_query)
            result = await tools["search_products"].ainvoke(
                {"query": query, "limit": 10}
            )
            products = result.get("products", [])
            if not products:
                catalog = await tools["search_products"].ainvoke(
                    {"query": "", "limit": 100}
                )
                terms = _search_terms(query)
                products = [
                    product
                    for product in catalog.get("products", [])
                    if terms
                    <= _search_terms(
                        f"{product.get('name', '')} {product.get('description', '')}"
                    )
                ]
            if not products:
                return {
                    "status": "cancelled",
                    "error": f"Nenhum produto encontrado: {query}.",
                }

            product = products[0]
            variant = _requested_variant(state.get("user_request", original_query))
            variant_id = requested.get("variant_id")
            variants = product.get("variants", [])
            matching_variant = next(
                (
                    item
                    for item in variants
                    if str(item.get("id")) == str(variant_id)
                    or str(item.get("name", "")).lower() == str(variant_id).lower()
                ),
                None,
            )
            if matching_variant is None and variant is not None:
                matching_variant = next(
                    (
                        item
                        for item in variants
                        if str(item.get("name", "")).lower() == variant
                    ),
                    None,
                )
            if matching_variant is not None:
                variant_id = matching_variant["id"]
            elif variant_id is not None:
                variant_id = None
            resolved_items.append(
                {
                    "product_id": product["id"],
                    "quantity": requested.get("quantity", 1),
                    "variant_id": variant_id,
                    "category": product.get("category", ""),
                }
            )
        return {"resolved_items": resolved_items, **resolved_items[0]}

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
        items = state.get("resolved_items", [])
        if not items and state.get("product_id") is not None:
            items = [
                {
                    "product_id": state["product_id"],
                    "quantity": state.get("quantity", 1),
                    "variant_id": state.get("variant_id"),
                }
            ]
        if not items:
            raise ValueError("O produto nao foi identificado.")
        cart = state.get("cart")
        for item in items:
            cart = await tools["add_to_cart"].ainvoke(item)
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
        categories = sorted(
            {
                item.get("category", "")
                for item in state.get("resolved_items", [])
                if item.get("category")
            }
        )
        try:
            policy = await tools["evaluate_payment"].ainvoke(
                {
                    "payer_account_id": state.get("payer_account_id", ""),
                    "amount": f"{instructions['amount']:.2f}",
                    "agent_id": state.get("agent_id", "default"),
                    "categories": categories,
                }
            )
        except RuntimeError as exc:
            return {"status": "cancelled", "error": str(exc)}
        return {
            "instructions": instructions,
            "payment_policy": policy,
            "status": "awaiting_approval"
            if policy.get("requires_human_approval")
            else "running",
        }

    def request_approval(state: PurchaseState) -> dict[str, Any]:
        instructions = state.get("instructions")
        checkout = state.get("checkout")
        if instructions is None or checkout is None:
            raise ValueError("As instrucoes de pagamento nao foram geradas.")
        policy = state.get("payment_policy", {})
        if not policy.get("requires_human_approval"):
            return {"status": "running", "human_approved": False}
        decision = interrupt(
            {
                "type": "payment_approval",
                "checkout_id": checkout["checkout_id"],
                "items": state.get("cart", {}).get("items", []),
                "amount": instructions["amount"],
                "payment_method": instructions["method"],
                "pix_code": instructions["pix_code"],
                "reason": policy.get("reason"),
                "checkout": checkout,
            }
        )
        if decision is True or decision == {"approved": True}:
            return {"status": "running", "human_approved": True}
        return {"status": "cancelled", "error": "Pagamento cancelado pelo usuario."}

    async def authorize_payment(state: PurchaseState) -> dict[str, Any]:
        instructions = state.get("instructions")
        payer_account_id = state.get("payer_account_id")
        agent_id = state.get("agent_id", "default")
        checkout = state.get("checkout")
        if instructions is None or payer_account_id is None or checkout is None:
            raise ValueError("Dados insuficientes para autorizar o pagamento.")
        human_approved = state.get("human_approved", False)
        policy = state.get("payment_policy", {})
        if policy.get("requires_human_approval") and not human_approved:
            decision = interrupt(
                {
                    "type": "payment_approval",
                    "question": "Deseja aprovar este pagamento? (sim/nao)",
                    "checkout_id": checkout["checkout_id"],
                    "items": state.get("cart", {}).get("items", []),
                    "amount": instructions["amount"],
                    "payment_method": instructions["method"],
                    "pix_code": instructions["pix_code"],
                    "reason": policy.get("reason"),
                    "checkout": checkout,
                }
            )
            if decision is not True and decision != {"approved": True}:
                return {
                    "status": "cancelled",
                    "error": "Pagamento cancelado pelo usuario.",
                }
            human_approved = True
        try:
            payment = await tools["authorize_payment"].ainvoke(
                {
                    "payer_account_id": payer_account_id,
                    "pix_code": instructions["pix_code"],
                    "amount": f"{instructions['amount']:.2f}",
                    "reference_id": checkout["checkout_id"],
                    "agent_id": agent_id,
                    "categories": sorted(
                        {
                            item.get("category", "")
                            for item in state.get("resolved_items", [])
                            if item.get("category")
                        }
                    ),
                    "human_approved": human_approved,
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
                "shipping_address": state.get("shipping_address"),
            }
        )
        return {"order": order, "status": "completed"}

    return locals()


def _after_search(state: PurchaseState) -> str:
    return END if state.get("status") == "cancelled" else "create_cart"


def _after_approval(state: PurchaseState) -> str:
    return END if state.get("status") == "cancelled" else "authorize_payment"


def _after_policy(state: PurchaseState) -> str:
    return END if state.get("status") == "cancelled" else "request_approval"


def _after_authorize_payment(state: PurchaseState) -> str:
    return END if state.get("status") == "cancelled" else "confirm_order"


def build_purchase_graph(
    model: BaseChatModel | None = None, tools: dict[str, Any] | None = None
):
    """Build the purchase graph. HTTP Mini Bank/Pix must already be running."""
    if tools is None:
        raise ValueError("As tools MCP devem ser fornecidas.")
    resolved_model = model or ChatOllama(
        model=os.environ.get("OLLAMA_MODEL", "qwen3:1.7b"),
        base_url=os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
        temperature=0,
    )
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
    graph.add_conditional_edges(
        "get_payment_instructions",
        _after_policy,
        {"request_approval": "request_approval", END: END},
    )
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
