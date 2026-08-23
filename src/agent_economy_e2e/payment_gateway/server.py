from __future__ import annotations

import os
from decimal import Decimal
from typing import Any

from mcp.server.mcpserver import MCPServer

from .app import authorize_payment as send_payment


class PaymentGatewayMCP(MCPServer):
    def __init__(self, bank_url: str | None = None) -> None:
        super().__init__("payment-gateway")
        resolved_url = bank_url or os.environ.get("MINI_BANK_URL")

        @self.tool()
        def authorize_payment(
            payer_account_id: str,
            pix_code: str,
            amount: str,
            reference_id: str,
        ) -> dict[str, Any]:
            """Authorize a BRL PIX payment through Mini Bank."""
            return send_payment(
                payer_account_id=payer_account_id,
                pix_code=pix_code,
                amount=Decimal(amount),
                reference_id=reference_id,
                bank_url=resolved_url,
            )


def build_server(bank_url: str | None = None) -> PaymentGatewayMCP:
    return PaymentGatewayMCP(bank_url)


def main() -> None:
    build_server().run()


if __name__ == "__main__":
    main()
