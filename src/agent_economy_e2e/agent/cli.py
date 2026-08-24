"""Backward-compatible imports for the former agent CLI module."""

from .. import main as _main

_approval_message = _main._approval_message
_payment_success_message = _main._payment_success_message
_public_result = _main._public_result
build_graph = _main.build_graph
close_mcp_tools = _main.close_mcp_tools


async def run(*args, **kwargs):
    original_build_graph = _main.build_graph
    original_close_mcp_tools = _main.close_mcp_tools

    async def build_graph_for_legacy_run(observer=None):
        return await build_graph()

    _main.build_graph = build_graph_for_legacy_run
    _main.close_mcp_tools = close_mcp_tools
    try:
        return await _main.run(*args, **kwargs)
    finally:
        _main.build_graph = original_build_graph
        _main.close_mcp_tools = original_close_mcp_tools


main = _main.main

__all__ = [
    "_approval_message",
    "_payment_success_message",
    "_public_result",
    "build_graph",
    "close_mcp_tools",
    "main",
    "run",
]
