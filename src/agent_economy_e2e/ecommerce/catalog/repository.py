from __future__ import annotations

from agent_economy_e2e.ecommerce.catalog.models import Product
from agent_economy_e2e.ecommerce.database.json_store import JsonStore


class CatalogRepository:
    def __init__(self, store: JsonStore) -> None:
        self._store = store

    def list_products(self) -> list[Product]:
        raw = self._store.read("catalog", [])
        return [Product.model_validate(item) for item in raw]

    def get_by_id(self, product_id: str) -> Product | None:
        for product in self.list_products():
            if product.id == product_id:
                return product
        return None
