from __future__ import annotations

from agent_economy_e2e.ecommerce.database.json_store import JsonStore
from agent_economy_e2e.ecommerce.payment.models import Payment


class PaymentRepository:
    def __init__(self, store: JsonStore) -> None:
        self._store = store

    def list_all(self) -> list[Payment]:
        return [Payment.model_validate(item) for item in self._store.read("payments", [])]

    def get(self, payment_id: str) -> Payment | None:
        for payment in self.list_all():
            if payment.id == payment_id:
                return payment
        return None

    def get_by_checkout(self, checkout_id: str) -> Payment | None:
        for payment in self.list_all():
            if payment.checkout_id == checkout_id:
                return payment
        return None

    def save(self, payment: Payment) -> Payment:
        items = self.list_all()
        payload = []
        updated = False
        for existing in items:
            if existing.id == payment.id:
                payload.append(payment)
                updated = True
            else:
                payload.append(existing)
        if not updated:
            payload.append(payment)
        self._store.write("payments", [p.model_dump(mode="json") for p in payload])
        return payment
