from __future__ import annotations

import ast
import json
import os
import sys
from contextlib import AsyncExitStack
from typing import Any, Callable

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

MCPObserver = Callable[
    [str, str, dict[str, Any], dict[str, Any] | None, Exception | None], None
]


class MCPTool:
    def __init__(
        self,
        session: ClientSession,
        name: str,
        observer: MCPObserver | None = None,
    ) -> None:
        self.session = session
        self.name = name
        self.observer = observer

    async def ainvoke(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if self.observer is not None:
            self.observer("start", self.name, arguments, None, None)
        try:
            result = await self.session.call_tool(self.name, arguments)
        except Exception as exc:
            if self.observer is not None:
                self.observer("error", self.name, arguments, None, exc)
            raise
        if getattr(result, "isError", False):
            message = next(
                (
                    item.text
                    for item in getattr(result, "content", [])
                    if getattr(item, "text", None)
                ),
                "MCP tool failed without a message",
            )
            error = RuntimeError(message)
            if self.observer is not None:
                self.observer("error", self.name, arguments, None, error)
            raise error

        structured = getattr(result, "structuredContent", None)
        if isinstance(structured, dict) and structured:
            if self.observer is not None:
                self.observer("success", self.name, arguments, structured, None)
            return structured

        for item in getattr(result, "content", []):
            text = getattr(item, "text", None)
            if text:
                try:
                    decoded = json.loads(text)
                except json.JSONDecodeError:
                    try:
                        decoded = ast.literal_eval(text)
                    except (SyntaxError, ValueError):
                        raise RuntimeError(str(text)) from None
                if isinstance(decoded, dict):
                    if self.observer is not None:
                        self.observer("success", self.name, arguments, decoded, None)
                    return decoded
        error = RuntimeError(f"Unexpected MCP result from {self.name}")
        if self.observer is not None:
            self.observer("error", self.name, arguments, None, error)
        raise error


class MCPToolset:
    def __init__(self) -> None:
        self.stack = AsyncExitStack()
        self.sessions: list[ClientSession] = []

    async def connect(self, observer: MCPObserver | None = None) -> dict[str, MCPTool]:
        configs = {
            "ecommerce": (
                "agent_economy_e2e.ecommerce.mcp.server",
                {
                    "ECOMMERCE_DATA_DIR": os.environ.get(
                        "ECOMMERCE_DATA_DIR", "data/ecommerce"
                    ),
                    "MINI_BANK_URL": os.environ.get(
                        "MINI_BANK_URL", "http://127.0.0.1:8000"
                    ),
                },
            ),
            "payment-gateway": (
                "agent_economy_e2e.payment_gateway.server",
                {
                    "MINI_BANK_URL": os.environ.get(
                        "MINI_BANK_URL", "http://127.0.0.1:8000"
                    ),
                },
            ),
        }
        tools: dict[str, MCPTool] = {}
        for module, environment in configs.values():
            params = StdioServerParameters(
                command=os.environ.get("PYTHON", sys.executable),
                args=["-m", module],
                env=os.environ.copy() | environment,
            )
            transport = await self.stack.enter_async_context(stdio_client(params))
            session = await self.stack.enter_async_context(ClientSession(*transport))
            await session.initialize()
            self.sessions.append(session)
            listed = await session.list_tools()
            for tool in listed.tools:
                tools[tool.name] = MCPTool(session, tool.name, observer)
        return tools

    async def close(self) -> None:
        await self.stack.aclose()


async def load_mcp_tools(observer: MCPObserver | None = None) -> dict[str, Any]:
    """Load tools from both MCP servers and keep their sessions alive."""
    global _toolset
    _toolset = MCPToolset()
    return await _toolset.connect(observer)


_toolset: MCPToolset | None = None


async def close_mcp_tools() -> None:
    global _toolset
    if _toolset is not None:
        await _toolset.close()
        _toolset = None
