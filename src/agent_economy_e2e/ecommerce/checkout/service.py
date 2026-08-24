from __future__ import annotations

from typing import Literal

from agent_economy_e2e.ecommerce.cart.service import CartService
from agent_economy_e2e.ecommerce.checkout.models import (
    SHIPPING_RATES,
    Checkout,
    CheckoutItem,
    CheckoutStatus,
    CheckoutView,
    ShippingAddress,
)
from agent_economy_e2e.ecommerce.checkout.repository import CheckoutRepository
from agent_economy_e2e.ecommerce.exceptions import NotFoundError, ValidationError
from agent_economy_e2e.ecommerce.ids import new_id


class CheckoutService:
    def __init__(self, repository: CheckoutRepository, carts: CartService) -> None:
        self._repository = repository
        self._carts = carts

    def create_checkout(
        self,
        cart_id: str,
        shipping_address: ShippingAddress,
        shipping_option: str = "standard",
        payment_method: Literal["pix"] = "pix",
    ) -> CheckoutView:
        if payment_method != "pix":
            raise ValidationError("payment_method must be 'pix'")
        if shipping_option not in SHIPPING_RATES:
            raise ValidationError(
                f"Invalid shipping_option. Use one of: {', '.join(SHIPPING_RATES)}"
            )
        if not shipping_address.street or not shipping_address.city:
            raise ValidationError("shipping_address is required")

        cart = self._carts.get_cart_by_id(cart_id)
        if not cart.items:
            raise ValidationError("Cannot create checkout from an empty cart")

        shipping = SHIPPING_RATES[shipping_option]
        totals = self._carts.calculate_for_cart(cart, shipping=shipping, discount=0.0)
        snapshot_items = [
            CheckoutItem(
                product_id=item.product_id,
                variant_id=item.variant_id,
                unit_price=item.unit_price,
                quantity=item.quantity,
            )
            for item in totals.items
        ]
        checkout = Checkout(
            id=new_id("chk"),
            cart_id=cart.id,
            items=snapshot_items,
            shipping_option=shipping_option,
            payment_method=payment_method,
            subtotal=totals.subtotal,
            shipping=totals.shipping,
            discount=totals.discount,
            total=totals.total,
            currency=totals.currency,
            status=CheckoutStatus.PAYMENT_PENDING,
        )
        saved = self._repository.save(checkout)
        return self.to_view(saved)

    def get_checkout(self, checkout_id: str) -> Checkout:
        checkout = self._repository.get(checkout_id)
        if checkout is None:
            raise NotFoundError(f"Checkout not found: {checkout_id}")
        return checkout

    def save(self, checkout: Checkout) -> Checkout:
        return self._repository.save(checkout)

    def to_view(self, checkout: Checkout) -> CheckoutView:
        return CheckoutView(
            checkout_id=checkout.id,
            subtotal=checkout.subtotal,
            shipping=checkout.shipping,
            discount=checkout.discount,
            total=checkout.total,
            currency=checkout.currency,
            payment_method=checkout.payment_method,
            status=checkout.status,
        )
