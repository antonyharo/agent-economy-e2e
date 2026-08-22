import pytest

from agent_economy_e2e.ecommerce.app import EcommerceApp
from agent_economy_e2e.ecommerce.exceptions import ConflictError, ValidationError


def test_create_cart(app: EcommerceApp) -> None:
    cart = app.cart.create_cart()
    assert cart.id.startswith("cart_")
    assert cart.items == []
    fetched = app.cart.get_cart()
    assert fetched.id == cart.id


def test_create_cart_fails_when_active_exists(app: EcommerceApp) -> None:
    app.cart.create_cart()
    with pytest.raises(ConflictError, match="already exists"):
        app.cart.create_cart()


def test_add_to_cart(app: EcommerceApp) -> None:
    app.cart.create_cart()
    cart = app.cart.add_to_cart("prod_tenis_x", quantity=2, variant_id="var_41")
    assert len(cart.items) == 1
    item = cart.items[0]
    assert item.product_id == "prod_tenis_x"
    assert item.quantity == 2
    assert item.unit_price == 799.9


def test_add_unavailable_product_fails(app: EcommerceApp) -> None:
    app.cart.create_cart()
    with pytest.raises(ValidationError, match="not available"):
        app.cart.add_to_cart("prod_jaqueta_esgotada")


def test_invalid_quantity_is_rejected(app: EcommerceApp) -> None:
    app.cart.create_cart()
    with pytest.raises(ValidationError, match="quantity must be >= 1"):
        app.cart.add_to_cart("prod_tenis_x", quantity=0)
    app.cart.add_to_cart("prod_tenis_x", quantity=1)
    with pytest.raises(ValidationError, match="quantity must be >= 1"):
        app.cart.update_cart_item("prod_tenis_x", quantity=-1)


def test_calculate_cart(app: EcommerceApp) -> None:
    app.cart.create_cart()
    app.cart.add_to_cart("prod_tenis_x", quantity=1)
    app.cart.add_to_cart("prod_camiseta_basica", quantity=2)
    totals = app.cart.calculate_cart()
    assert totals.subtotal == 979.7
    assert totals.shipping == 20.0
    assert totals.discount == 0.0
    assert totals.total == 999.7
    assert totals.currency == "BRL"
