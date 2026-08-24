from __future__ import annotations

from typing import Any

from langchain_core.language_models import BaseChatModel

from .graph import build_purchase_graph


def agent(
    *,
    tools: dict[str, Any],
    model: BaseChatModel | None = None,
):
    """Build the purchase agent with its MCP tools and optional model."""
    return build_purchase_graph(model=model, tools=tools)


__all__ = ["agent"]
