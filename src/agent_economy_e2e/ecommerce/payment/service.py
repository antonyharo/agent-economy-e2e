from __future__ import annotations

from abc import ABC, abstractmethod

from agent_economy_e2e.ecommerce.checkout.models import CheckoutStatus
from agent_economy_e2e.ecommerce.checkout.service import CheckoutService
from agent_economy_e2e.ecommerce.exceptions import NotFoundError, ValidationError
from agent_economy_e2e.ecommerce.ids import new_id
from agent_economy_e2e.ecommerce.payment.models import (
    Payment,
    PaymentInstructions,
    PaymentStatus,
    PaymentStatusView,
)
from agent_economy_e2e.ecommerce.payment.repository import PaymentRepository


class PaymentService(ABC):
    """Payment port. The sandbox implementation can later be replaced by Mini Pix."""

    @abstractmethod
    def get_payment_instructions(self, checkout_id: str) -> PaymentInstructions:
        raise NotImplementedError

    @abstractmethod
    def get_payment_status(self, checkout_id: str) -> PaymentStatusView:
        raise NotImplementedError

    @abstractmethod
    def get_payment(self, payment_id: str) -> Payment:
        raise NotImplementedError

    @abstractmethod
    def simulate_payment(self, payment_id: str) -> PaymentStatusView:
        raise NotImplementedError


class SimulatedPixPaymentService(PaymentService):
    def __init__(self, repository: PaymentRepository, checkouts: CheckoutService) -> None:
        self._repository = repository
        self._checkouts = checkouts

    def get_payment_instructions(self, checkout_id: str) -> PaymentInstructions:
        checkout = self._checkouts.get_checkout(checkout_id)
        existing = self._repository.get_by_checkout(checkout_id)
        if existing is not None:
            return self._to_instructions(existing)

        payment = Payment(
            id=new_id("pay"),
            checkout_id=checkout.id,
            method="pix",
            amount=checkout.total,
            currency=checkout.currency,
            pix_code=f"PIX_SIMULATED_{checkout.id}_{checkout.total:.2f}",
            status=PaymentStatus.PENDING,
        )
        saved = self._repository.save(payment)
        checkout.payment_id = saved.id
        if checkout.status == CheckoutStatus.CREATED:
            checkout.status = CheckoutStatus.PAYMENT_PENDING
        self._checkouts.save(checkout)
        return self._to_instructions(saved)

    def get_payment_status(self, checkout_id: str) -> PaymentStatusView:
        checkout = self._checkouts.get_checkout(checkout_id)
        payment = self._repository.get_by_checkout(checkout_id)
        if payment is None:
            raise NotFoundError(f"No payment instructions for checkout: {checkout.id}")
        return self._to_status(payment)

    def get_payment(self, payment_id: str) -> Payment:
        payment = self._repository.get(payment_id)
        if payment is None:
            raise NotFoundError(f"Payment not found: {payment_id}")
        return payment

    def simulate_payment(self, payment_id: str) -> PaymentStatusView:
        payment = self.get_payment(payment_id)
        if payment.status == PaymentStatus.PAID:
            return self._to_status(payment)
        if payment.status in {PaymentStatus.FAILED, PaymentStatus.EXPIRED}:
            raise ValidationError(f"Cannot pay a {payment.status} payment")

        payment.status = PaymentStatus.PAID
        saved = self._repository.save(payment)
        checkout = self._checkouts.get_checkout(saved.checkout_id)
        checkout.status = CheckoutStatus.PAID
        checkout.payment_id = saved.id
        self._checkouts.save(checkout)
        return self._to_status(saved)

    def _to_instructions(self, payment: Payment) -> PaymentInstructions:
        return PaymentInstructions(
            payment_id=payment.id,
            method=payment.method,
            amount=payment.amount,
            currency=payment.currency,
            pix_code=payment.pix_code,
            status=payment.status,
        )

    def _to_status(self, payment: Payment) -> PaymentStatusView:
        return PaymentStatusView(
            payment_id=payment.id,
            checkout_id=payment.checkout_id,
            status=payment.status,
            amount=payment.amount,
            currency=payment.currency,
        )
