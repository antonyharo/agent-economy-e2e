# Ecommerce MCP sandbox (agent-ready)

MVP de um servidor MCP de ecommerce em Python. O servidor expõe tools para catálogo, carrinho, checkout, pagamento PIX simulado e pedido. Persistência em arquivos JSON. Sem autenticação, sem frontend e sem integração com pagamentos reais.

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

| Tool | Função |
| --- | --- |
| `search_products` | Busca somente leitura no catálogo (cursor pagination) |
| `create_cart` / `get_cart` | Um cart ativo por agente |
| `add_to_cart` / `update_cart_item` / `remove_from_cart` / `clear_cart` | Mutação do cart |
| `calculate_cart` | Subtotal, frete, desconto e total calculados no servidor |
| `create_checkout` | Snapshot da compra (`payment_method` apenas `pix`) |
| `get_payment_instructions` | PIX simulado (`PIX_SIMULATED_...`) |
| `get_payment_status` | Estado do pagamento |
| `simulate_pix_payment` | Sandbox: marca o PIX como pago |
| `confirm_order` | Confirma o pedido se o pagamento estiver `paid` |

Preços e totais são sempre calculados pelo servidor. O agente não informa valor de pagamento nem sobrescreve o total.

## Fluxo

`Cart` → `Checkout` (snapshot) → `Payment` (PIX simulado) → `Order`

Pagamento é abstraído em `PaymentService` (`SimulatedPixPaymentService` neste MVP), para troca futura pelo Mini Pix.

## Dados seed

Produtos de demonstração em `src/agent_economy_e2e/ecommerce/database/seed_catalog.json` (Tênis X, Camiseta Básica, Mochila Urban e um item indisponível).
