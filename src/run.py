from __future__ import annotations

import argparse
import ast
import asyncio
import datetime
import json
import os
import socket
import subprocess
import sys
from contextlib import AsyncExitStack, nullcontext
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOG = ROOT / "e2e_run.log"
TOOL_DESCRIPTIONS = {
    "search_products": "Busca um produto disponivel no catalogo.",
    "create_cart": "Cria o carrinho ativo do agente.",
    "add_to_cart": "Adiciona o produto escolhido ao carrinho.",
    "calculate_cart": "Calcula subtotal, frete e total no servidor.",
    "create_checkout": "Cria o snapshot do checkout com pagamento PIX.",
    "get_payment_instructions": "Cria a cobranca PIX e retorna suas instrucoes.",
    "authorize_payment": "Autoriza o pagamento PIX pelo gateway financeiro.",
    "confirm_order": "Confirma o pedido apos reconciliar o pagamento pago.",
}


class Logger:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.file = path.open("w", encoding="utf-8")

    def write(self, message: str) -> None:
        timestamp = datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")
        self.file.write(f"{timestamp} {message}\n")
        self.file.flush()

    def close(self) -> None:
        self.file.close()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str, sort_keys=True)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def _http_request(
    logger: Logger,
    method: str,
    url: str,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = None if body is None else json.dumps(body).encode("utf-8")
    logger.write(f"HTTP REQUEST {method} {url} {_json(body or {})}")

    def request() -> dict[str, Any]:
        request_object = Request(
            url,
            data=payload,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request_object, timeout=2) as response:
            return json.loads(response.read().decode("utf-8"))

    result = await asyncio.to_thread(request)
    logger.write(f"HTTP OUTPUT {method} {url} {_json(result)}")
    return result


async def _wait_for_service(logger: Logger, url: str) -> None:
    for attempt in range(1, 31):
        try:
            await _http_request(logger, "GET", url)
            return
        except (URLError, OSError, TimeoutError) as exc:
            logger.write(f"HTTP RETRY {url} attempt={attempt} error={exc}")
            await asyncio.sleep(0.2)
    raise RuntimeError(f"Service did not become ready: {url}")


def _start_http_service(
    logger: Logger,
    name: str,
    module: str,
    port: int,
    env: dict[str, str],
) -> subprocess.Popen[bytes]:
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        f"{module}:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--log-level",
        "warning",
    ]
    logger.write(f"PROCESS START {name} {_json(command)}")
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    return process


def _mcp_params(module: str, env: dict[str, str]) -> StdioServerParameters:
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", module],
        env=env,
        cwd=ROOT,
    )


def _tool_output(result: Any) -> dict[str, Any]:
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict) and structured:
        return structured
    for item in getattr(result, "content", []):
        text = getattr(item, "text", None)
        if text:
            try:
                decoded = json.loads(text)
            except json.JSONDecodeError:
                decoded = ast.literal_eval(text)
            if isinstance(decoded, dict):
                return decoded
    raise RuntimeError(f"Unexpected MCP result: {result!r}")


async def _call_tool(
    logger: Logger,
    session: ClientSession,
    server_name: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    logger.write(
        f"TOOL ACTION {server_name}.{tool_name} "
        f"{TOOL_DESCRIPTIONS.get(tool_name, 'Executa uma operacao MCP.')}"
    )
    logger.write(f"TOOL REQUEST {server_name}.{tool_name} {_json(arguments)}")
    result = await session.call_tool(tool_name, arguments)
    if getattr(result, "isError", False):
        logger.write(f"TOOL ERROR {server_name}.{tool_name} {_json(result)}")
        raise RuntimeError(f"MCP tool failed: {server_name}.{tool_name}")
    output = _tool_output(result)
    logger.write(f"TOOL OUTPUT {server_name}.{tool_name} {_json(output)}")
    return output


async def run(log_path: Path) -> dict[str, Any]:
    logger = Logger(log_path)
    processes: list[tuple[str, subprocess.Popen[bytes]]] = []
    try:
        with nullcontext(ROOT / "data") as data_root:
            data_root.mkdir(parents=True, exist_ok=True)
            pix_port = _free_port()
            bank_port = _free_port()
            pix_url = f"http://127.0.0.1:{pix_port}"
            bank_url = f"http://127.0.0.1:{bank_port}"
            base_env = os.environ.copy()
            bank_data_dir = data_root / "mini-bank"
            bank_data_dir.mkdir(parents=True, exist_ok=True)
            accounts_path = bank_data_dir / "accounts.json"
            if not accounts_path.exists():
                accounts_path.write_text(
                    json.dumps(
                        [
                            {
                                "account_id": "buyer",
                                "balance": "1000.00",
                                "currency": "BRL",
                            },
                            {
                                "account_id": "seller",
                                "balance": "50.00",
                                "currency": "BRL",
                            },
                        ],
                        indent=2,
                    ),
                    encoding="utf-8",
                )

            pix_env = base_env | {"MINI_PIX_DATA_DIR": str(data_root / "mini-pix")}
            bank_env = base_env | {
                "MINI_BANK_DATA_DIR": str(bank_data_dir),
                "MINI_PIX_URL": pix_url,
            }
            processes.append(
                (
                    "mini-pix",
                    _start_http_service(
                        logger,
                        "mini-pix",
                        "agent_economy_e2e.mini_pix.app",
                        pix_port,
                        pix_env,
                    ),
                )
            )
            processes.append(
                (
                    "mini-bank",
                    _start_http_service(
                        logger,
                        "mini-bank",
                        "agent_economy_e2e.mini_bank.app",
                        bank_port,
                        bank_env,
                    ),
                )
            )
            await _wait_for_service(logger, f"{pix_url}/openapi.json")
            await _wait_for_service(logger, f"{bank_url}/accounts/buyer/balance")

            ecommerce_env = base_env | {
                "ECOMMERCE_DATA_DIR": str(data_root / "ecommerce"),
                # The current ecommerce server uses this setting for its bank URL.
                "MINI_PIX_URL": bank_url,
            }
            gateway_env = base_env | {"MINI_BANK_URL": bank_url}

            logger.write("MCP CONNECT ecommerce")
            logger.write("MCP CONNECT payment-gateway")
            async with AsyncExitStack() as stack:
                ecommerce_transport = await stack.enter_async_context(
                    stdio_client(
                        _mcp_params(
                            "agent_economy_e2e.ecommerce.mcp.server", ecommerce_env
                        ),
                        errlog=logger.file,
                    )
                )
                ecommerce = await stack.enter_async_context(
                    ClientSession(*ecommerce_transport)
                )
                gateway_transport = await stack.enter_async_context(
                    stdio_client(
                        _mcp_params(
                            "agent_economy_e2e.payment_gateway.server", gateway_env
                        ),
                        errlog=logger.file,
                    )
                )
                gateway = await stack.enter_async_context(
                    ClientSession(*gateway_transport)
                )
                await ecommerce.initialize()
                await gateway.initialize()
                logger.write("MCP INITIALIZED ecommerce and payment-gateway")

                products = await _call_tool(
                    logger,
                    ecommerce,
                    "ecommerce",
                    "search_products",
                    {"query": "Tênis"},
                )
                product_id = products["products"][0]["id"]
                cart = await _call_tool(
                    logger, ecommerce, "ecommerce", "create_cart", {}
                )
                await _call_tool(
                    logger,
                    ecommerce,
                    "ecommerce",
                    "add_to_cart",
                    {"product_id": product_id, "quantity": 1, "variant_id": "var_42"},
                )
                totals = await _call_tool(
                    logger, ecommerce, "ecommerce", "calculate_cart", {}
                )
                checkout = await _call_tool(
                    logger,
                    ecommerce,
                    "ecommerce",
                    "create_checkout",
                    {
                        "cart_id": cart["id"],
                        "shipping_address": {
                            "street": "Rua das Flores",
                            "number": "123",
                            "city": "Sao Paulo",
                            "state": "SP",
                            "postal_code": "01000-000",
                            "country": "BR",
                        },
                        "shipping_option": "standard",
                        "payment_method": "pix",
                    },
                )
                instructions = await _call_tool(
                    logger,
                    ecommerce,
                    "ecommerce",
                    "get_payment_instructions",
                    {"checkout_id": checkout["checkout_id"]},
                )
                invoice = await _call_tool(
                    logger,
                    gateway,
                    "payment-gateway",
                    "authorize_payment",
                    {
                        "payer_account_id": "buyer",
                        "pix_code": instructions["pix_code"],
                        "amount": f"{instructions['amount']:.2f}",
                        "reference_id": checkout["checkout_id"],
                    },
                )
                order = await _call_tool(
                    logger,
                    ecommerce,
                    "ecommerce",
                    "confirm_order",
                    {
                        "checkout_id": checkout["checkout_id"],
                        "payment_id": instructions["payment_id"],
                    },
                )
                output = {
                    "cart": cart,
                    "totals": totals,
                    "checkout": checkout,
                    "invoice": invoice,
                    "order": order,
                }
                logger.write(f"E2E COMPLETE {_json(output)}")
                return output
    except Exception as exc:
        logger.write(f"E2E ERROR {type(exc).__name__}: {exc}")
        raise
    finally:
        for name, process in reversed(processes):
            logger.write(f"PROCESS STOP {name}")
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            logger.write(f"PROCESS EXIT {name} code={process.returncode}")
        logger.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Executa o fluxo E2E do ecommerce via MCP."
    )
    parser.add_argument(
        "--log", type=Path, default=DEFAULT_LOG, help="Arquivo de log do fluxo."
    )
    args = parser.parse_args()
    result = asyncio.run(run(args.log.resolve()))
    print(f"Fluxo E2E concluido: order_id={result['order']['order_id']}")
    print(f"Log: {args.log.resolve()}")


if __name__ == "__main__":
    main()
