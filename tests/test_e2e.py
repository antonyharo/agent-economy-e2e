from agent_economy_e2e.ecommerce.app import EcommerceApp
from agent_economy_e2e.ecommerce.payment.models import PaymentStatus
from tests.helpers import ADDRESS


def test_e2e_search_to_confirmed_order(app: EcommerceApp) -> None:
    search = app.catalog.search(query="Tênis")
    product = search.products[0]
    assert product.id == "prod_tenis_x"

    cart = app.cart.create_cart()
    app.cart.add_to_cart(product.id, quantity=1, variant_id="var_42")
    totals = app.cart.calculate_cart()
    assert totals.subtotal == 799.9
    assert totals.total == 819.9

    checkout = app.checkout.create_checkout(
        cart_id=cart.id,
        shipping_address=ADDRESS,
        shipping_option="standard",
        payment_method="pix",
    )
    assert checkout.total == 819.9
    assert checkout.status == "payment_pending"

    instructions = app.payment.get_payment_instructions(checkout.checkout_id)
    assert instructions.pix_code.startswith("PIX_SIMULATED_")
    assert instructions.amount == checkout.total

    app.payment.simulate_payment(instructions.payment_id)
    status = app.payment.get_payment_status(checkout.checkout_id)
    assert status.status == PaymentStatus.PAID

    order = app.order.confirm_order(checkout.checkout_id, instructions.payment_id)
    assert order.status == "confirmed"
    assert app.checkout.get_checkout(checkout.checkout_id).status == "confirmed"
