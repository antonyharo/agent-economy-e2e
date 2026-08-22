from __future__ import annotations

import os
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from agent_economy_e2e.ecommerce.app import EcommerceApp, create_app
from agent_economy_e2e.ecommerce.mcp.tools import register_tools

DEFAULT_DATA_DIR = Path("data")


class EcommerceMCP(MCPServer):
    def __init__(self, app: EcommerceApp) -> None:
        super().__init__("ecommerce")
        self.app = app
        register_tools(self, app)


def build_server(data_dir: Path | None = None) -> EcommerceMCP:
    resolved = data_dir or Path(os.environ.get("ECOMMERCE_DATA_DIR", DEFAULT_DATA_DIR))
    app = create_app(resolved)
    return EcommerceMCP(app)


def main() -> None:
    build_server().run()


if __name__ == "__main__":
    main()
