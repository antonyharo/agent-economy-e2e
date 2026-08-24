from __future__ import annotations

import os
from decimal import Decimal
from typing import Any

from mcp.server.mcpserver import MCPServer

from .app import authorize_payment as send_payment
from .app import evaluate_payment as check_payment


class PaymentGatewayMCP(MCPServer):
    def __init__(self, bank_url: str | None = None) -> None:
        super().__init__("payment-gateway")
        resolved_url = bank_url or os.environ.get("MINI_BANK_URL")

        @self.tool()
        def evaluate_payment(
            payer_account_id: str,
            amount: str,
            agent_id: str = "default",
            categories: list[str] | None = None,
            category: str | None = None,
        ) -> dict[str, Any]:
            """Evaluate policy and report whether human pre-approval is required."""
            return check_payment(
                payer_account_id=payer_account_id,
                amount=Decimal(amount),
                agent_id=agent_id,
                categories=categories,
                category=category,
            )

        @self.tool()
        def authorize_payment(
            payer_account_id: str,
            pix_code: str,
            amount: str,
            reference_id: str,
            agent_id: str = "default",
            categories: list[str] | None = None,
            category: str | None = None,
            human_approved: bool = False,
        ) -> dict[str, Any]:
            """Authorize a BRL PIX payment after validating the agent policy."""
            return send_payment(
                payer_account_id=payer_account_id,
                pix_code=pix_code,
                amount=Decimal(amount),
                reference_id=reference_id,
                bank_url=resolved_url,
                agent_id=agent_id,
                categories=categories,
                category=category,
                human_approved=human_approved,
            )


def build_server(bank_url: str | None = None) -> PaymentGatewayMCP:
    return PaymentGatewayMCP(bank_url)


def main() -> None:
    build_server().run()


if __name__ == "__main__":
    main()
