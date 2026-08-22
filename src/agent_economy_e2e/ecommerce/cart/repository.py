from __future__ import annotations

from agent_economy_e2e.ecommerce.cart.models import Cart, CartStatus
from agent_economy_e2e.ecommerce.database.json_store import JsonStore


class CartRepository:
    def __init__(self, store: JsonStore) -> None:
        self._store = store

    def list_all(self) -> list[Cart]:
        return [Cart.model_validate(item) for item in self._store.read("carts", [])]

    def get(self, cart_id: str) -> Cart | None:
        for cart in self.list_all():
            if cart.id == cart_id:
                return cart
        return None

    def get_active(self, agent_id: str) -> Cart | None:
        for cart in self.list_all():
            if cart.agent_id == agent_id and cart.status == CartStatus.ACTIVE:
                return cart
        return None

    def save(self, cart: Cart) -> Cart:
        carts = self.list_all()
        updated = False
        payload = []
        for existing in carts:
            if existing.id == cart.id:
                payload.append(cart)
                updated = True
            else:
                payload.append(existing)
        if not updated:
            payload.append(cart)
        self._store.write("carts", [c.model_dump(mode="json") for c in payload])
        return cart
