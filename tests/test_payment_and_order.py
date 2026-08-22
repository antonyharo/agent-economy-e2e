import pytest

from agent_economy_e2e.ecommerce.app import EcommerceApp
from agent_economy_e2e.ecommerce.exceptions import ValidationError
from agent_economy_e2e.ecommerce.payment.models import PaymentStatus
from tests.helpers import ADDRESS


def _paid_and_pending_checkouts(app: EcommerceApp) -> tuple[str, str, str, str]:
    cart = app.cart.create_cart()
    app.cart.add_to_cart("prod_tenis_x", quantity=1)
    first = app.checkout.create_checkout(cart_id=cart.id, shipping_address=ADDRESS)
    second = app.checkout.create_checkout(cart_id=cart.id, shipping_address=ADDRESS)
    pay1 = app.payment.get_payment_instructions(first.checkout_id)
    pay2 = app.payment.get_payment_instructions(second.checkout_id)
    app.payment.simulate_payment(pay1.payment_id)
    return first.checkout_id, pay1.payment_id, second.checkout_id, pay2.payment_id


def test_get_pix_instructions(app: EcommerceApp) -> None:
    cart = app.cart.create_cart()
    app.cart.add_to_cart("prod_tenis_x", quantity=1)
    checkout = app.checkout.create_checkout(cart_id=cart.id, shipping_address=ADDRESS)
    instructions = app.payment.get_payment_instructions(checkout.checkout_id)
    assert instructions.payment_id.startswith("pay_")
    assert instructions.method == "pix"
    assert instructions.amount == 819.9
    assert instructions.currency == "BRL"
    assert instructions.pix_code.startswith("PIX_SIMULATED_")
    assert instructions.status == PaymentStatus.PENDING


def test_get_payment_status(app: EcommerceApp) -> None:
    cart = app.cart.create_cart()
    app.cart.add_to_cart("prod_tenis_x", quantity=1)
    checkout = app.checkout.create_checkout(cart_id=cart.id, shipping_address=ADDRESS)
    instructions = app.payment.get_payment_instructions(checkout.checkout_id)
    status = app.payment.get_payment_status(checkout.checkout_id)
    assert status.payment_id == instructions.payment_id
    assert status.status == PaymentStatus.PENDING


def test_confirm_order_with_paid_payment(app: EcommerceApp) -> None:
    checkout_id, payment_id, _, _ = _paid_and_pending_checkouts(app)
    order = app.order.confirm_order(checkout_id, payment_id)
    assert order.order_id.startswith("ord_")
    assert order.checkout_id == checkout_id
    assert order.payment_id == payment_id
    assert order.status == "confirmed"
    again = app.order.confirm_order(checkout_id, payment_id)
    assert again.order_id == order.order_id


def test_cannot_confirm_pending_payment(app: EcommerceApp) -> None:
    _, _, checkout_id, payment_id = _paid_and_pending_checkouts(app)
    with pytest.raises(ValidationError, match="must be paid"):
        app.order.confirm_order(checkout_id, payment_id)


def test_cannot_confirm_with_payment_from_another_checkout(app: EcommerceApp) -> None:
    checkout_id, _, _, other_payment_id = _paid_and_pending_checkouts(app)
    with pytest.raises(ValidationError, match="does not belong"):
        app.order.confirm_order(checkout_id, other_payment_id)
