import asyncio
from pathlib import Path

from agent_economy_e2e.ecommerce.mcp.server import build_server


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
        "get_payment_status",
        "simulate_pix_payment",
        "confirm_order",
        "confirm_order_after_payment",
    }
