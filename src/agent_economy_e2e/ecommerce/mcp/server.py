from __future__ import annotations

import os
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from agent_economy_e2e.ecommerce.app import EcommerceApp, create_app
from agent_economy_e2e.ecommerce.mcp.tools import register_tools

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data" / "ecommerce"


class EcommerceMCP(MCPServer):
    def __init__(self, app: EcommerceApp) -> None:
        super().__init__("ecommerce")
        self.app = app
        register_tools(self, app)


def build_server(data_dir: Path | None = None) -> EcommerceMCP:
    resolved = data_dir or Path(os.environ.get("ECOMMERCE_DATA_DIR", DEFAULT_DATA_DIR))
    app = create_app(resolved, os.environ.get("MINI_BANK_URL", "http://127.0.0.1:8000"))
    return EcommerceMCP(app)


def main() -> None:
    build_server().run()


if __name__ == "__main__":
    main()
