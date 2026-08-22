import pytest

from agent_economy_e2e.ecommerce.app import EcommerceApp
from agent_economy_e2e.ecommerce.exceptions import ValidationError
from tests.helpers import ADDRESS


def _cart_with_item(app: EcommerceApp) -> str:
    cart = app.cart.create_cart()
    app.cart.add_to_cart("prod_tenis_x", quantity=1)
    return cart.id


def test_create_checkout(app: EcommerceApp) -> None:
    cart_id = _cart_with_item(app)
    checkout = app.checkout.create_checkout(
        cart_id=cart_id,
        shipping_address=ADDRESS,
        shipping_option="standard",
        payment_method="pix",
    )
    assert checkout.checkout_id.startswith("chk_")
    assert checkout.subtotal == 799.9
    assert checkout.shipping == 20.0
    assert checkout.discount == 0.0
    assert checkout.total == 819.9
    assert checkout.payment_method == "pix"
    assert checkout.status == "payment_pending"


def test_checkout_is_a_snapshot(app: EcommerceApp) -> None:
    cart_id = _cart_with_item(app)
    checkout = app.checkout.create_checkout(cart_id=cart_id, shipping_address=ADDRESS)
    app.cart.add_to_cart("prod_mochila_urban", quantity=1)
    stored = app.checkout.get_checkout(checkout.checkout_id)
    assert stored.total == 819.9
    assert len(stored.items) == 1


def test_cannot_checkout_empty_cart(app: EcommerceApp) -> None:
    cart = app.cart.create_cart()
    with pytest.raises(ValidationError, match="empty cart"):
        app.checkout.create_checkout(cart_id=cart.id, shipping_address=ADDRESS)
