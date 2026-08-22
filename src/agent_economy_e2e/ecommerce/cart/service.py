from __future__ import annotations

from agent_economy_e2e.ecommerce.cart.models import Cart, CartItem, CartStatus, CartTotals
from agent_economy_e2e.ecommerce.cart.repository import CartRepository
from agent_economy_e2e.ecommerce.catalog.models import Product
from agent_economy_e2e.ecommerce.catalog.service import CatalogService
from agent_economy_e2e.ecommerce.exceptions import ConflictError, NotFoundError, ValidationError
from agent_economy_e2e.ecommerce.ids import new_id
from agent_economy_e2e.ecommerce.money import money

DEFAULT_SHIPPING = 20.0
DEFAULT_DISCOUNT = 0.0
DEFAULT_AGENT_ID = "default"


class CartService:
    def __init__(self, repository: CartRepository, catalog: CatalogService) -> None:
        self._repository = repository
        self._catalog = catalog

    def create_cart(self, agent_id: str = DEFAULT_AGENT_ID) -> Cart:
        if self._repository.get_active(agent_id) is not None:
            raise ConflictError("An active cart already exists")
        cart = Cart(id=new_id("cart"), agent_id=agent_id, status=CartStatus.ACTIVE)
        return self._repository.save(cart)

    def get_cart(self, agent_id: str = DEFAULT_AGENT_ID) -> Cart:
        cart = self._repository.get_active(agent_id)
        if cart is None:
            raise NotFoundError("No active cart")
        return cart

    def get_cart_by_id(self, cart_id: str) -> Cart:
        cart = self._repository.get(cart_id)
        if cart is None:
            raise NotFoundError(f"Cart not found: {cart_id}")
        return cart

    def add_to_cart(
        self,
        product_id: str,
        quantity: int = 1,
        variant_id: str | None = None,
        agent_id: str = DEFAULT_AGENT_ID,
    ) -> Cart:
        self._validate_quantity(quantity)
        cart = self.get_cart(agent_id)
        product = self._catalog.get_product(product_id)
        self._assert_product_available(product, variant_id)

        for item in cart.items:
            if item.product_id == product_id and item.variant_id == variant_id:
                item.quantity += quantity
                item.unit_price = product.price
                item.name = product.name
                return self._repository.save(cart)

        cart.items.append(
            CartItem(
                product_id=product.id,
                variant_id=variant_id,
                name=product.name,
                unit_price=product.price,
                quantity=quantity,
                currency=product.currency,
            )
        )
        return self._repository.save(cart)

    def update_cart_item(
        self,
        product_id: str,
        quantity: int,
        variant_id: str | None = None,
        agent_id: str = DEFAULT_AGENT_ID,
    ) -> Cart:
        self._validate_quantity(quantity)
        cart = self.get_cart(agent_id)
        item = self._find_item(cart, product_id, variant_id)
        product = self._catalog.get_product(product_id)
        self._assert_product_available(product, variant_id)
        item.quantity = quantity
        item.unit_price = product.price
        item.name = product.name
        return self._repository.save(cart)

    def remove_from_cart(
        self,
        product_id: str,
        variant_id: str | None = None,
        agent_id: str = DEFAULT_AGENT_ID,
    ) -> Cart:
        cart = self.get_cart(agent_id)
        self._find_item(cart, product_id, variant_id)
        cart.items = [
            item
            for item in cart.items
            if not (item.product_id == product_id and item.variant_id == variant_id)
        ]
        return self._repository.save(cart)

    def clear_cart(self, agent_id: str = DEFAULT_AGENT_ID) -> Cart:
        cart = self.get_cart(agent_id)
        cart.items = []
        return self._repository.save(cart)

    def calculate_cart(
        self,
        agent_id: str = DEFAULT_AGENT_ID,
        shipping: float = DEFAULT_SHIPPING,
        discount: float = DEFAULT_DISCOUNT,
    ) -> CartTotals:
        cart = self.get_cart(agent_id)
        return self.calculate_for_cart(cart, shipping=shipping, discount=discount)

    def calculate_for_cart(
        self,
        cart: Cart,
        shipping: float = DEFAULT_SHIPPING,
        discount: float = DEFAULT_DISCOUNT,
    ) -> CartTotals:
        priced_items: list[CartItem] = []
        subtotal = 0.0
        for item in cart.items:
            product = self._catalog.get_product(item.product_id)
            unit_price = product.price
            priced = item.model_copy(
                update={"unit_price": unit_price, "name": product.name, "currency": product.currency}
            )
            priced_items.append(priced)
            subtotal = money(subtotal + unit_price * priced.quantity)

        shipping = money(shipping)
        discount = money(discount)
        total = money(subtotal + shipping - discount)
        currency = priced_items[0].currency if priced_items else "BRL"
        return CartTotals(
            cart_id=cart.id,
            subtotal=subtotal,
            shipping=shipping,
            discount=discount,
            total=total,
            currency=currency,
            items=priced_items,
        )

    def mark_checked_out(self, cart_id: str) -> None:
        cart = self.get_cart_by_id(cart_id)
        cart.status = CartStatus.CHECKED_OUT
        self._repository.save(cart)

    def _validate_quantity(self, quantity: int) -> None:
        if quantity < 1:
            raise ValidationError("quantity must be >= 1")

    def _find_item(self, cart: Cart, product_id: str, variant_id: str | None) -> CartItem:
        for item in cart.items:
            if item.product_id == product_id and item.variant_id == variant_id:
                return item
        raise NotFoundError("Cart item not found")

    def _assert_product_available(self, product: Product, variant_id: str | None) -> None:
        if not product.available:
            raise ValidationError(f"Product is not available: {product.id}")
        if variant_id is None:
            return
        variant = next((v for v in product.variants if v.id == variant_id), None)
        if variant is None:
            raise NotFoundError(f"Variant not found: {variant_id}")
        if not variant.available:
            raise ValidationError(f"Variant is not available: {variant_id}")
