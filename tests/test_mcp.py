import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent_economy_e2e.ecommerce.mcp.server import build_server
from run import _tool_output


def test_mcp_tools_are_registered(tmp_path: Path) -> None:
    server = build_server(tmp_path)
    tools = asyncio.run(server.list_tools())
    names = {tool.name for tool in tools}
    assert names == {
        "search_products",
        "get_cart",
        "create_cart",
        "add_to_cart",
        "update_cart_item",
        "remove_from_cart",
        "clear_cart",
        "calculate_cart",
        "create_checkout",
        "get_payment_instructions",
        "confirm_order",
    }


def test_tool_output_preserves_textual_mcp_error() -> None:
    result = SimpleNamespace(
        structuredContent=None,
        content=[
            SimpleNamespace(
                text="Error executing tool create_cart: An active cart already exists"
            )
        ],
    )

    with pytest.raises(
        RuntimeError,
        match="Error executing tool create_cart: An active cart already exists",
    ):
        _tool_output(result)
