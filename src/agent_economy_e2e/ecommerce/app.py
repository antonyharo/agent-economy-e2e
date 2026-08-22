from __future__ import annotations

from pathlib import Path

from agent_economy_e2e.ecommerce.cart.repository import CartRepository
from agent_economy_e2e.ecommerce.cart.service import CartService
from agent_economy_e2e.ecommerce.catalog.repository import CatalogRepository
from agent_economy_e2e.ecommerce.catalog.service import CatalogService
from agent_economy_e2e.ecommerce.checkout.repository import CheckoutRepository
from agent_economy_e2e.ecommerce.checkout.service import CheckoutService
from agent_economy_e2e.ecommerce.database.json_store import JsonStore
from agent_economy_e2e.ecommerce.database.seed import ensure_seed_data
from agent_economy_e2e.ecommerce.order.repository import OrderRepository
from agent_economy_e2e.ecommerce.order.service import OrderService
from agent_economy_e2e.ecommerce.payment.repository import PaymentRepository
from agent_economy_e2e.ecommerce.payment.service import PaymentService, SimulatedPixPaymentService


class EcommerceApp:
    def __init__(
        self,
        catalog: CatalogService,
        cart: CartService,
        checkout: CheckoutService,
        payment: PaymentService,
        order: OrderService,
    ) -> None:
        self.catalog = catalog
        self.cart = cart
        self.checkout = checkout
        self.payment = payment
        self.order = order


def create_app(data_dir: Path) -> EcommerceApp:
    ensure_seed_data(data_dir)
    store = JsonStore(data_dir)
    catalog = CatalogService(CatalogRepository(store))
    cart = CartService(CartRepository(store), catalog)
    checkout = CheckoutService(CheckoutRepository(store), cart)
    payment: PaymentService = SimulatedPixPaymentService(PaymentRepository(store), checkout)
    order = OrderService(OrderRepository(store), checkout, payment, cart)
    return EcommerceApp(
        catalog=catalog,
        cart=cart,
        checkout=checkout,
        payment=payment,
        order=order,
    )
