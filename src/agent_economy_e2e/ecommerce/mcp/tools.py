from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from agent_economy_e2e.ecommerce.app import EcommerceApp
from agent_economy_e2e.ecommerce.catalog.models import ProductSearchFilters
from agent_economy_e2e.ecommerce.checkout.models import ShippingAddress
from agent_economy_e2e.ecommerce.exceptions import EcommerceError


def _dump(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="json")


def _filters(filters: dict[str, Any] | None) -> ProductSearchFilters:
    if filters is None:
        return ProductSearchFilters()
    try:
        return ProductSearchFilters.model_validate(filters)
    except PydanticValidationError as exc:
        raise EcommerceError(f"Invalid filters: {exc}") from exc


def _address(shipping_address: dict[str, Any]) -> ShippingAddress:
    try:
        return ShippingAddress.model_validate(shipping_address)
    except PydanticValidationError as exc:
        raise EcommerceError(f"Invalid shipping_address: {exc}") from exc


def register_tools(mcp: MCPServer, app: EcommerceApp) -> None:
    @mcp.tool()
    def search_products(
        query: str = "",
        filters: dict[str, Any] | None = None,
        sort: str | None = None,
        limit: int = 10,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """Search the product catalog. Prices come from the catalog and cannot be changed."""
        return _dump(
            app.catalog.search(
                query=query,
                filters=_filters(filters),
                sort=sort,
                limit=limit,
                cursor=cursor,
            )
        )

    @mcp.tool()
    def get_cart() -> dict[str, Any]:
        """Return the active cart for this agent."""
        return _dump(app.cart.get_cart())

    @mcp.tool()
    def create_cart() -> dict[str, Any]:
        """Create an active cart. Fails if one already exists."""
        return _dump(app.cart.create_cart())

    @mcp.tool()
    def add_to_cart(
        product_id: str,
        quantity: int = 1,
        variant_id: str | None = None,
    ) -> dict[str, Any]:
        """Add an available catalog product to the active cart."""
        return _dump(
            app.cart.add_to_cart(
                product_id=product_id, quantity=quantity, variant_id=variant_id
            )
        )

    @mcp.tool()
    def update_cart_item(
        product_id: str,
        quantity: int,
        variant_id: str | None = None,
    ) -> dict[str, Any]:
        """Update quantity of a cart item. Quantity must be >= 1."""
        return _dump(
            app.cart.update_cart_item(
                product_id=product_id, quantity=quantity, variant_id=variant_id
            )
        )

    @mcp.tool()
    def remove_from_cart(
        product_id: str,
        variant_id: str | None = None,
    ) -> dict[str, Any]:
        """Remove an item from the active cart."""
        return _dump(
            app.cart.remove_from_cart(product_id=product_id, variant_id=variant_id)
        )

    @mcp.tool()
    def clear_cart() -> dict[str, Any]:
        """Remove all items from the active cart."""
        return _dump(app.cart.clear_cart())

    @mcp.tool()
    def calculate_cart() -> dict[str, Any]:
        """Calculate subtotal, shipping, discount and total on the server."""
        return _dump(app.cart.calculate_cart())

    @mcp.tool()
    def create_checkout(
        cart_id: str,
        shipping_address: dict[str, Any],
        shipping_option: str = "standard",
        payment_method: str = "pix",
    ) -> dict[str, Any]:
        """Create a checkout snapshot from a non-empty cart. Totals are calculated by the server."""
        if payment_method != "pix":
            raise EcommerceError("payment_method must be 'pix'")
        return _dump(
            app.checkout.create_checkout(
                cart_id=cart_id,
                shipping_address=_address(shipping_address),
                shipping_option=shipping_option,
                payment_method="pix",
            )
        )

    @mcp.tool()
    def get_payment_instructions(checkout_id: str) -> dict[str, Any]:
        """Create or return real Mini Pix instructions for a checkout."""
        return _dump(app.payment.get_payment_instructions(checkout_id))


    @mcp.tool()
    def confirm_order(
        checkout_id: str,
        payment_id: str,
        shipping_address: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Confirm an order only when the sandbox payment is paid and matches the checkout."""
        return _dump(
            app.order.confirm_order(
                checkout_id=checkout_id,
                payment_id=payment_id,
                shipping_address=(
                    _address(shipping_address) if shipping_address is not None else None
                ),
            )
        )
