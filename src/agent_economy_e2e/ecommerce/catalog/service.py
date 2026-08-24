from __future__ import annotations

import base64
import json
import re
import unicodedata

from agent_economy_e2e.ecommerce.catalog.models import (
    Product,
    ProductSearchFilters,
    ProductSearchResult,
    ProductSummary,
)
from agent_economy_e2e.ecommerce.catalog.repository import CatalogRepository
from agent_economy_e2e.ecommerce.exceptions import NotFoundError, ValidationError

VALID_SORTS = {"price_asc", "price_desc", "name_asc", "name_desc"}


class CatalogService:
    def __init__(self, repository: CatalogRepository) -> None:
        self._repository = repository

    def get_product(self, product_id: str) -> Product:
        product = self._repository.get_by_id(product_id)
        if product is None:
            raise NotFoundError(f"Product not found: {product_id}")
        return product

    def search(
        self,
        query: str = "",
        filters: ProductSearchFilters | None = None,
        sort: str | None = None,
        limit: int = 10,
        cursor: str | None = None,
    ) -> ProductSearchResult:
        if limit < 1:
            raise ValidationError("limit must be >= 1")
        filters = filters or ProductSearchFilters()
        if sort is not None and sort not in VALID_SORTS:
            raise ValidationError(
                f"Invalid sort '{sort}'. Use one of: {', '.join(sorted(VALID_SORTS))}"
            )

        products = self._repository.list_products()
        products = [p for p in products if self._matches(p, query, filters)]
        products = self._sort(products, sort)

        offset = self._decode_cursor(cursor)
        page = products[offset : offset + limit]
        next_cursor = None
        if offset + limit < len(products):
            next_cursor = self._encode_cursor(offset + limit)

        return ProductSearchResult(
            products=[
                ProductSummary(
                    id=p.id,
                    name=p.name,
                    price=p.price,
                    currency=p.currency,
                    available=p.available,
                    category=p.category,
                    variants=p.variants,
                )
                for p in page
            ],
            next_cursor=next_cursor,
        )

    def _matches(
        self, product: Product, query: str, filters: ProductSearchFilters
    ) -> bool:
        query_terms = self._search_terms(query)
        if query_terms:
            haystack_terms = self._search_terms(
                f"{product.name} {product.description} {product.category} {product.id}"
            )
            if not all(term in haystack_terms for term in query_terms):
                return False
        if filters.category and product.category.lower() != filters.category.lower():
            return False
        if filters.min_price is not None and product.price < filters.min_price:
            return False
        if filters.max_price is not None and product.price > filters.max_price:
            return False
        if filters.available is not None and product.available != filters.available:
            return False
        return True

    def _search_terms(self, value: str) -> set[str]:
        plain = "".join(
            character
            for character in unicodedata.normalize("NFD", value.lower())
            if unicodedata.category(character) != "Mn"
        )
        terms = set(re.findall(r"[a-z0-9]+", plain))
        return {
            term[:-1] if len(term) > 3 and term.endswith("s") else term
            for term in terms
        }

    def _sort(self, products: list[Product], sort: str | None) -> list[Product]:
        if sort == "price_asc":
            return sorted(products, key=lambda p: (p.price, p.name))
        if sort == "price_desc":
            return sorted(products, key=lambda p: (-p.price, p.name))
        if sort == "name_desc":
            return sorted(products, key=lambda p: p.name.lower(), reverse=True)
        return sorted(products, key=lambda p: p.name.lower())

    def _encode_cursor(self, offset: int) -> str:
        payload = json.dumps({"offset": offset}, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(payload).decode()

    def _decode_cursor(self, cursor: str | None) -> int:
        if not cursor:
            return 0
        try:
            raw = base64.urlsafe_b64decode(cursor.encode())
            offset = int(json.loads(raw)["offset"])
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            raise ValidationError("Invalid cursor") from exc
        if offset < 0:
            raise ValidationError("Invalid cursor")
        return offset
