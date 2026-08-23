from __future__ import annotations

from agent_economy_e2e.ecommerce.cart.models import CartStatus
from agent_economy_e2e.ecommerce.cart.service import CartService
from agent_economy_e2e.ecommerce.checkout.models import CheckoutStatus
from agent_economy_e2e.ecommerce.checkout.service import CheckoutService
from agent_economy_e2e.ecommerce.exceptions import ValidationError
from agent_economy_e2e.ecommerce.ids import new_id
from agent_economy_e2e.ecommerce.money import money
from agent_economy_e2e.ecommerce.order.models import (
    Order,
    OrderConfirmation,
    OrderStatus,
)
from agent_economy_e2e.ecommerce.order.repository import OrderRepository
from agent_economy_e2e.ecommerce.payment.models import PaymentStatus
from agent_economy_e2e.ecommerce.payment.service import PaymentService


class OrderService:
    def __init__(
        self,
        repository: OrderRepository,
        checkouts: CheckoutService,
        payments: PaymentService,
        carts: CartService,
    ) -> None:
        self._repository = repository
        self._checkouts = checkouts
        self._payments = payments
        self._carts = carts

    def confirm_order(self, checkout_id: str, payment_id: str) -> OrderConfirmation:
        checkout = self._checkouts.get_checkout(checkout_id)
        payment = self._payments.get_payment(payment_id)

        existing = self._repository.get_by_checkout(checkout.id)
        if existing is not None:
            if existing.payment_id != payment_id:
                raise ValidationError(
                    "Checkout already confirmed with a different payment"
                )
            return self._to_view(existing)

        if payment.checkout_id != checkout.id:
            raise ValidationError("payment_id does not belong to the given checkout")
        if payment.status != PaymentStatus.PAID:
            raise ValidationError(
                f"Payment must be paid to confirm the order (current: {payment.status})"
            )
        if money(payment.amount) != money(checkout.total):
            raise ValidationError("Paid amount does not match checkout total")

        order = Order(
            id=new_id("ord"),
            checkout_id=checkout.id,
            payment_id=payment.id,
            status=OrderStatus.CONFIRMED,
            items=checkout.items,
            shipping_address=checkout.shipping_address,
            total=checkout.total,
            currency=checkout.currency,
        )
        saved = self._repository.save(order)
        checkout.status = CheckoutStatus.CONFIRMED
        checkout.payment_id = payment.id
        checkout.order_id = saved.id
        self._checkouts.save(checkout)

        cart = self._carts.get_cart_by_id(checkout.cart_id)
        if cart.status == CartStatus.ACTIVE:
            self._carts.mark_checked_out(cart.id)

        return self._to_view(saved)

    def confirm_order_after_payment(
        self,
        checkout_id: str,
        payment_id: str,
        transaction_id: str,
        invoice_id: str,
    ) -> OrderConfirmation:
        if not invoice_id or not invoice_id.startswith("invoice-"):
            raise ValidationError("invoice_id is invalid")
        checkout = self._checkouts.get_checkout(checkout_id)
        payment = self._payments.get_payment(payment_id)
        if payment.checkout_id != checkout.id:
            raise ValidationError("payment_id does not belong to the given checkout")
        if payment.transaction_id != transaction_id:
            raise ValidationError("transaction_id does not match payment")
        if money(payment.amount) != money(checkout.total):
            raise ValidationError("Paid amount does not match checkout total")

        existing = self._repository.get_by_checkout(checkout.id)
        if existing is not None:
            if (
                existing.payment_id != payment_id
                or payment.invoice_id != invoice_id
                or payment.transaction_id != transaction_id
            ):
                raise ValidationError(
                    "Checkout already confirmed with different payment data"
                )
            return self._to_view(existing)

        self._payments.mark_external_payment_paid(
            payment_id, transaction_id, invoice_id
        )
        return self.confirm_order(checkout_id, payment_id)

    def _to_view(self, order: Order) -> OrderConfirmation:
        return OrderConfirmation(
            order_id=order.id,
            checkout_id=order.checkout_id,
            payment_id=order.payment_id,
            status=order.status,
        )
