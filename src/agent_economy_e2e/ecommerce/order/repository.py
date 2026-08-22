from __future__ import annotations

from agent_economy_e2e.ecommerce.database.json_store import JsonStore
from agent_economy_e2e.ecommerce.order.models import Order


class OrderRepository:
    def __init__(self, store: JsonStore) -> None:
        self._store = store

    def list_all(self) -> list[Order]:
        return [Order.model_validate(item) for item in self._store.read("orders", [])]

    def get(self, order_id: str) -> Order | None:
        for order in self.list_all():
            if order.id == order_id:
                return order
        return None

    def get_by_checkout(self, checkout_id: str) -> Order | None:
        for order in self.list_all():
            if order.checkout_id == checkout_id:
                return order
        return None

    def save(self, order: Order) -> Order:
        items = self.list_all()
        payload = []
        updated = False
        for existing in items:
            if existing.id == order.id:
                payload.append(order)
                updated = True
            else:
                payload.append(existing)
        if not updated:
            payload.append(order)
        self._store.write("orders", [o.model_dump(mode="json") for o in payload])
        return order
