# Ecommerce MCP sandbox (agent-ready)

MVP de um servidor MCP de ecommerce em Python. O servidor expõe tools para catálogo, carrinho, checkout, cobrança PIX via Mini Pix e pedido. Persistência em arquivos JSON. Sem autenticação e sem frontend.

O SDK MCP 2.x usa `MCPServer` (sucessor do FastMCP do SDK oficial).

## Requisitos

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) (recomendado) ou `pip`

## Instalação

```bash
uv sync --extra dev
```

Com pip:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

## Executar o servidor MCP

O servidor usa transporte stdio (padrão MCP):

```bash
uv run ecommerce-mcp
```

Alternativas:

```bash
uv run python -m agent_economy_e2e
uv run app
```

Diretório de dados (catálogo seed + JSON de runtime):

```bash
set ECOMMERCE_DATA_DIR=data
uv run ecommerce-mcp
```

Na primeira execução o seed do catálogo é copiado para `catalog.json` nesse diretório.

### Cursor / cliente MCP

Exemplo de configuração:

```json
{
  "mcpServers": {
    "ecommerce": {
      "command": "uv",
      "args": ["run", "ecommerce-mcp"],
      "env": {
        "ECOMMERCE_DATA_DIR": "data"
      }
    }
  }
}
```

## Testes

```bash
uv run pytest
```

## Tools MCP

| Tool                                                                   | Função                                                   |
| ---------------------------------------------------------------------- | -------------------------------------------------------- |
| `search_products`                                                      | Busca somente leitura no catálogo (cursor pagination)    |
| `create_cart` / `get_cart`                                             | Um cart ativo por agente                                 |
| `add_to_cart` / `update_cart_item` / `remove_from_cart` / `clear_cart` | Mutação do cart                                          |
| `calculate_cart`                                                       | Subtotal, frete, desconto e total calculados no servidor |
| `create_checkout`                                                      | Snapshot da compra (`payment_method` apenas `pix`)       |
| `get_payment_instructions`                                             | Cria ou retorna uma cobrança real no Mini Pix            |
| `get_payment_status`                                                   | Estado do pagamento                                      |
| `simulate_pix_payment`                                                 | Sandbox: marca o PIX como pago                           |
| `confirm_order`                                                        | Confirma o pedido se o pagamento estiver `paid`          |
| `confirm_order_after_payment`                                          | Confirma o pedido com transaction/invoice do Gateway     |

Preços e totais são sempre calculados pelo servidor. O agente não informa valor de pagamento nem sobrescreve o total.

## Infraestrutura financeira

A infraestrutura financeira é independente do ecommerce e tem três processos:

```text
Payment Gateway (MCP) -> Mini Bank (HTTP) -> Mini Pix (HTTP interno)
```

O Mini Bank movimenta saldo em BRL. O Mini Pix gerencia charges, transactions e invoices; ele nunca altera saldos. O Gateway valida os parâmetros e chama somente o Mini Bank.

Inicie cada componente em um terminal separado:

```bash
uv run python -m agent_economy_e2e.mini_pix.app
uv run python -m agent_economy_e2e.mini_bank.app
uv run payment-gateway-mcp
```

Os serviços escutam em `127.0.0.1:8001`, `127.0.0.1:8000` e transporte MCP stdio, respectivamente. Para alterar os diretórios JSON ou a URL interna, use `MINI_PIX_DATA_DIR`, `MINI_BANK_DATA_DIR`, `MINI_PIX_URL` e `MINI_BANK_URL`.

Exemplo de fluxo E2E:

```text
authorize_payment("buyer", "PIX-TEST-SELLER-25", Decimal("25.00"), "payment-1")
  -> Mini Bank resolve a cobrança no Mini Pix
  -> verifica buyer = 100.00
  -> debita buyer e credita seller
  -> Mini Pix completa a transaction e gera a invoice
  -> buyer = 75.00, seller = 75.00
```

Para executar todos os testes, incluindo os financeiros:

```bash
uv run pytest
```

## Fluxo

`Cart` → `Checkout` (snapshot) → `Payment` (cobrança Mini Pix) → `Order`

Pagamento é abstraído em `PaymentService`. A aplicação MCP usa `RealPixPaymentService`; `SimulatedPixPaymentService` permanece disponível para compatibilidade dos testes e do fluxo legado.

## Dados seed

Produtos de demonstração em `src/agent_economy_e2e/ecommerce/database/seed_catalog.json` (Tênis X, Camiseta Básica, Mochila Urban e um item indisponível).
