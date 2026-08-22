from __future__ import annotations

from agent_economy_e2e.ecommerce.checkout.models import Checkout
from agent_economy_e2e.ecommerce.database.json_store import JsonStore


class CheckoutRepository:
    def __init__(self, store: JsonStore) -> None:
        self._store = store

    def list_all(self) -> list[Checkout]:
        return [Checkout.model_validate(item) for item in self._store.read("checkouts", [])]

    def get(self, checkout_id: str) -> Checkout | None:
        for checkout in self.list_all():
            if checkout.id == checkout_id:
                return checkout
        return None

    def save(self, checkout: Checkout) -> Checkout:
        items = self.list_all()
        payload = []
        updated = False
        for existing in items:
            if existing.id == checkout.id:
                payload.append(checkout)
                updated = True
            else:
                payload.append(existing)
        if not updated:
            payload.append(checkout)
        self._store.write("checkouts", [c.model_dump(mode="json") for c in payload])
        return checkout
