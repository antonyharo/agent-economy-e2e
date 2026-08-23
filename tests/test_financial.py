import socket
import threading
import time
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import uvicorn
from fastapi.testclient import TestClient

from agent_economy_e2e.ecommerce.app import create_financial_app
from agent_economy_e2e.ecommerce.payment.models import PaymentStatus
from agent_economy_e2e.mini_bank.app import check_balance, credit_account, debit_account
from agent_economy_e2e.mini_bank.app import create_app as create_bank_app
from agent_economy_e2e.mini_pix.app import (
    complete_transaction,
    create_charge,
    generate_invoice,
    resolve_pix_code,
)
from agent_economy_e2e.mini_pix.app import create_app as create_pix_app
from agent_economy_e2e.payment_gateway.app import authorize_payment
from agent_economy_e2e.payment_gateway.server import build_server
from tests.helpers import ADDRESS


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _start_http(app, port: int) -> tuple[uvicorn.Server, threading.Thread]:
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.01)
    assert server.started
    return server, thread


def test_mini_pix_charge_resolution_completion_and_invoice(tmp_path: Path) -> None:
    charge = create_charge("tx-1", "seller", Decimal("25.00"), tmp_path)
    assert resolve_pix_code(charge.pix_code, tmp_path).receiver_account_id == "seller"
    completed = complete_transaction("tx-1", tmp_path)
    assert completed.status == "COMPLETED"
    assert generate_invoice("tx-1", tmp_path).status == "COMPLETED"
    assert (
        generate_invoice("tx-1", tmp_path).invoice_id
        == generate_invoice("tx-1", tmp_path).invoice_id
    )


def test_mini_bank_creates_mini_pix_charge_with_uuid_txid(tmp_path: Path) -> None:
    pix_port = _free_port()
    pix_server, pix_thread = _start_http(create_pix_app(tmp_path / "pix"), pix_port)
    try:
        bank = create_bank_app(tmp_path / "bank", f"http://127.0.0.1:{pix_port}")
        response = TestClient(bank).post(
            "/charges",
            json={"receiver_account_id": "seller", "amount": "25.00"},
        )

        assert response.status_code == 200
        charge = response.json()
        assert charge["receiver_account_id"] == "seller"
        assert charge["amount"] == "25.00"
        assert charge["transaction_id"]
        assert UUID(charge["transaction_id"])
        assert (
            resolve_pix_code(charge["pix_code"], tmp_path / "pix").transaction_id
            == charge["transaction_id"]
        )
    finally:
        pix_server.should_exit = True
        pix_thread.join(timeout=5)


def test_mini_bank_balance_debit_credit_and_insufficient_balance(
    tmp_path: Path,
) -> None:
    bank = create_bank_app(tmp_path, "http://127.0.0.1:8001")
    client = TestClient(bank)
    assert client.get("/accounts/buyer/balance").json()["balance"] == "100.00"
    debit_account("buyer", Decimal("25.00"), "tx-1", tmp_path)
    credit_account("seller", Decimal("25.00"), "tx-1", tmp_path)
    assert check_balance("buyer", tmp_path).balance == Decimal("75.00")
    assert check_balance("seller", tmp_path).balance == Decimal("75.00")
    debit_account("buyer", Decimal("25.00"), "tx-1", tmp_path)
    assert check_balance("buyer", tmp_path).balance == Decimal("75.00")


def test_mini_bank_rejects_insufficient_balance(tmp_path: Path) -> None:
    try:
        debit_account("buyer", Decimal("101.00"), "tx-1", tmp_path)
    except ValueError as exc:
        assert "insufficient" in str(exc)
    else:
        raise AssertionError("insufficient balance should fail")
    assert check_balance("buyer", tmp_path).balance == Decimal("100.00")


def test_mcp_exposes_only_expected_payment_tool() -> None:
    import asyncio

    tools = asyncio.run(build_server("http://127.0.0.1:8000").list_tools())
    assert [tool.name for tool in tools] == ["authorize_payment"]


def test_payment_flow_uses_mini_bank_and_mini_pix_over_http(tmp_path: Path) -> None:
    pix_dir = tmp_path / "pix"
    bank_dir = tmp_path / "bank"
    charge = create_charge("tx-http", "seller", Decimal("25.00"), pix_dir)
    pix_port = _free_port()
    bank_port = _free_port()
    pix_server, pix_thread = _start_http(create_pix_app(pix_dir), pix_port)
    bank_server, bank_thread = _start_http(
        create_bank_app(bank_dir, f"http://127.0.0.1:{pix_port}"), bank_port
    )
    try:
        invoice = authorize_payment(
            "buyer",
            charge.pix_code,
            Decimal("25.00"),
            "reference-not-transaction",
            f"http://127.0.0.1:{bank_port}",
        )
        retry_invoice = authorize_payment(
            "buyer",
            charge.pix_code,
            Decimal("25.00"),
            "another-reference",
            f"http://127.0.0.1:{bank_port}",
        )
        assert invoice["status"] == "COMPLETED"
        assert retry_invoice["invoice_id"] == invoice["invoice_id"]
        assert check_balance("buyer", bank_dir).balance == Decimal("75.00")
        assert check_balance("seller", bank_dir).balance == Decimal("75.00")
    finally:
        bank_server.should_exit = True
        pix_server.should_exit = True
        bank_thread.join(timeout=5)
        pix_thread.join(timeout=5)


def test_ecommerce_financial_mcp_flow(tmp_path: Path) -> None:
    pix_dir = tmp_path / "pix"
    bank_dir = tmp_path / "bank"
    bank_dir.mkdir()
    (bank_dir / "accounts.json").write_text(
        '[{"account_id": "buyer", "balance": "200.00", "currency": "BRL"}, '
        '{"account_id": "seller", "balance": "50.00", "currency": "BRL"}]',
        encoding="utf-8",
    )
    pix_port = _free_port()
    bank_port = _free_port()
    pix_server, pix_thread = _start_http(create_pix_app(pix_dir), pix_port)
    bank_server, bank_thread = _start_http(
        create_bank_app(bank_dir, f"http://127.0.0.1:{pix_port}"), bank_port
    )
    try:
        ecommerce = create_financial_app(
            tmp_path / "ecommerce", f"http://127.0.0.1:{pix_port}"
        )
        cart = ecommerce.cart.create_cart()
        ecommerce.cart.add_to_cart("prod_camiseta_basica", quantity=1)
        checkout = ecommerce.checkout.create_checkout(cart.id, ADDRESS)
        instructions = ecommerce.payment.get_payment_instructions(checkout.checkout_id)
        charge = resolve_pix_code(instructions.pix_code, pix_dir)
        assert instructions.pix_code == charge.pix_code
        assert checkout.total == 109.9

        invoice = authorize_payment(
            "buyer",
            instructions.pix_code,
            Decimal(str(checkout.total)),
            checkout.checkout_id,
            f"http://127.0.0.1:{bank_port}",
        )
        assert invoice["status"] == "COMPLETED"
        assert invoice["amount"] == "109.90"

        order = ecommerce.order.confirm_order_after_payment(
            checkout.checkout_id,
            instructions.payment_id,
            invoice["transaction_id"],
            invoice["invoice_id"],
        )
        assert order.status == "confirmed"
        assert (
            ecommerce.checkout.get_checkout(checkout.checkout_id).status == "confirmed"
        )
        assert (
            ecommerce.payment.get_payment(instructions.payment_id).status
            == PaymentStatus.PAID
        )
        assert check_balance("buyer", bank_dir).balance == Decimal("90.10")
        assert check_balance("seller", bank_dir).balance == Decimal("159.90")
    finally:
        bank_server.should_exit = True
        pix_server.should_exit = True
        bank_thread.join(timeout=5)
        pix_thread.join(timeout=5)
