from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

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

DEFAULT_MINI_BANK_URL = "http://127.0.0.1:8001"
DEFAULT_RECEIVER_ACCOUNT_ID = "seller"


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

    @abstractmethod
    def mark_external_payment_paid(
        self, payment_id: str, transaction_id: str, invoice_id: str
    ) -> Payment:
        raise NotImplementedError


class SimulatedPixPaymentService(PaymentService):
    def __init__(
        self, repository: PaymentRepository, checkouts: CheckoutService
    ) -> None:
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

    def mark_external_payment_paid(
        self, payment_id: str, transaction_id: str, invoice_id: str
    ) -> Payment:
        payment = self.get_payment(payment_id)
        if payment.transaction_id != transaction_id:
            raise ValidationError("transaction_id does not match payment")
        payment.invoice_id = invoice_id
        payment.status = PaymentStatus.PAID
        return self._repository.save(payment)

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


class RealPixPaymentService(SimulatedPixPaymentService):
    def __init__(
        self,
        repository: PaymentRepository,
        checkouts: CheckoutService,
        mini_bank_url: str | None = None,
    ) -> None:
        super().__init__(repository, checkouts)
        self._mini_bank_url = mini_bank_url or os.environ.get(
            "MINI_BANK_URL", DEFAULT_MINI_BANK_URL
        )

    def get_payment_instructions(self, checkout_id: str) -> PaymentInstructions:
        checkout = self._checkouts.get_checkout(checkout_id)
        existing = self._repository.get_by_checkout(checkout_id)
        if existing is not None:
            return self._to_instructions(existing)

        payload = {
            "receiver_account_id": DEFAULT_RECEIVER_ACCOUNT_ID,
            "amount": f"{checkout.total:.2f}",
            "currency": checkout.currency,
        }
        charge = self._create_charge(payload)
        payment = Payment(
            id=new_id("pay"),
            checkout_id=checkout.id,
            method="pix",
            amount=checkout.total,
            currency=checkout.currency,
            pix_code=charge["pix_code"],
            transaction_id=charge["transaction_id"],
            status=PaymentStatus.PENDING,
        )
        saved = self._repository.save(payment)
        checkout.payment_id = saved.id
        if checkout.status == CheckoutStatus.CREATED:
            checkout.status = CheckoutStatus.PAYMENT_PENDING
        self._checkouts.save(checkout)
        return self._to_instructions(saved)

    def _create_charge(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = Request(
            f"{self._mini_bank_url.rstrip('/')}/charges",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=5) as response:
                return json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError) as exc:
            raise ValidationError(f"Mini Pix request failed: {exc}") from exc

    
    def _to_instructions(self, payment: Payment) -> PaymentInstructions:
        return PaymentInstructions(
            payment_id=payment.id,
            method=payment.method,
            amount=payment.amount,
            currency=payment.currency,
            pix_code=payment.pix_code,
            status=payment.status,
        )
