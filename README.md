# Ecommerce MCP sandbox

Sandbox de ecommerce orientado a agentes, implementado em Python. A aplicação expõe operações de catálogo, carrinho, checkout, cobrança PIX e confirmação de pedido através de MCP. A persistência é feita em arquivos JSON e não há autenticação nem frontend.

O projeto também inclui uma infraestrutura financeira local composta por Mini Bank, Mini Pix e Payment Gateway.

## Requisitos

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) recomendado, ou `pip`

## Instalação

Com `uv`:

```bash
uv sync --extra dev
```

Com `pip`:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

## Funcionalidades

- Busca de produtos com consulta, filtros, ordenação, limite e paginação por cursor.
- Criação e consulta de um carrinho ativo por agente.
- Inclusão, atualização, remoção e limpeza de itens do carrinho.
- Cálculo server-side de subtotal, frete, desconto e total.
- Criação de checkout como snapshot do carrinho.
- Pagamento por PIX real através do Mini Pix e do Payment Gateway.
- Confirmação do pedido somente depois da reconciliação do pagamento.
- Operações idempotentes no processamento financeiro.
- Dados de catálogo inicializados a partir de `seed_catalog.json`.

Os preços e totais são calculados pelo servidor. O agente não pode sobrescrever o valor do produto ou do pagamento.

## Tools MCP

O servidor Ecommerce MCP usa transporte stdio e registra estas tools:

| Tool                       | Função                                          |
| -------------------------- | ----------------------------------------------- |
| `search_products`          | Busca produtos no catálogo.                     |
| `get_cart`                 | Retorna o carrinho ativo.                       |
| `create_cart`              | Cria um carrinho ativo.                         |
| `add_to_cart`              | Adiciona um produto disponível.                 |
| `update_cart_item`         | Atualiza a quantidade de um item.               |
| `remove_from_cart`         | Remove um item.                                 |
| `clear_cart`               | Remove todos os itens.                          |
| `calculate_cart`           | Calcula os valores do carrinho.                 |
| `create_checkout`          | Cria um checkout com endereço e opção de frete. |
| `get_payment_instructions` | Cria ou recupera a cobrança PIX.                |
| `confirm_order`            | Confirma o pedido com pagamento aprovado.       |

O Payment Gateway MCP registra uma tool:

| Tool                | Função                                          |
| ------------------- | ----------------------------------------------- |
| `authorize_payment` | Autoriza um pagamento PIX através do Mini Bank. |

O método de pagamento aceito pelo checkout MCP é `pix`.

## Modo 1: servidor Ecommerce MCP

Inicie o servidor via entry point:

```bash
uv run ecommerce-mcp
```

Alternativas:

```bash
uv run python -m agent_economy_e2e
uv run app
```

Exemplo de configuração para um cliente MCP:

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

## Modo 2: infraestrutura financeira manual

A infraestrutura financeira possui três processos:

```text
Payment Gateway (MCP) -> Mini Bank (HTTP) -> Mini Pix (HTTP)
```

Em terminais separados, execute:

```bash
uv run python -m agent_economy_e2e.mini_pix.app
uv run python -m agent_economy_e2e.mini_bank.app
uv run payment-gateway-mcp
```

Por padrão:

- Mini Pix escuta em `127.0.0.1:8001`.
- Mini Bank escuta em `127.0.0.1:8000`.
- Payment Gateway usa transporte MCP stdio.

O Mini Bank movimenta saldos em BRL. O Mini Pix administra cobranças, transações e invoices, mas não altera saldos. O Gateway valida a solicitação e encaminha o pagamento ao Mini Bank.

## Modo 3: fluxo E2E automatizado

O runner [src/run.py](src/run.py) inicia automaticamente Mini Pix, Mini Bank, Ecommerce MCP e Payment Gateway MCP. Em seguida executa:

```text
search_products
 -> create_cart
 -> add_to_cart
 -> calculate_cart
 -> create_checkout
 -> get_payment_instructions
 -> authorize_payment
 -> confirm_order
```

Execute a partir da raiz do projeto:

```bash
uv run python src/run.py
```

O runner escolhe portas livres e usa os dados persistidos em `data/`, com saldo suficiente para o comprador na primeira execução.

Por padrão, cada execução grava um log detalhado em `e2e_run.log`. É possível escolher outro arquivo:

```bash
uv run python src/run.py --log logs/meu-fluxo.txt
```

O log contém timestamps, descrições das ações, requisições e respostas MCP, requisições e respostas HTTP, erros e ciclo de vida dos processos.

## Configuração

| Variável             | Uso                                      | Padrão                  |
| -------------------- | ---------------------------------------- | ----------------------- |
| `ECOMMERCE_DATA_DIR` | Diretório dos JSONs do Ecommerce MCP.    | `data/ecommerce`        |
| `MINI_BANK_DATA_DIR` | Diretório dos JSONs do Mini Bank.        | `data/mini-bank`        |
| `MINI_PIX_DATA_DIR`  | Diretório dos JSONs do Mini Pix.         | `data/mini-pix`         |
| `MINI_BANK_URL`      | URL do Mini Bank usada pelo Gateway MCP. | Definida pelo ambiente  |
| `MINI_PIX_URL`       | URL financeira usada pelos serviços.     | `http://127.0.0.1:8001` |

No runner, a configuração é montada automaticamente por processo. Devido ao contrato atual do Ecommerce MCP, `MINI_PIX_URL` recebe a URL do Mini Bank nesse processo para que `confirm_order` consiga consultar a cobrança reconciliada. Em execução manual, mantenha essa mesma ligação entre Ecommerce MCP e Mini Bank.

## Persistência

O Ecommerce MCP grava coleções como `catalog.json`, `carts.json`, `checkouts.json`, `payments.json` e `orders.json` em `data/ecommerce` por padrão.

O Mini Bank grava `accounts.json` em `data/mini-bank`, e o Mini Pix grava `charges.json`, `transactions.json` e `invoices.json` em `data/mini-pix`. Os caminhos podem ser substituídos pelas variáveis de ambiente correspondentes.

No runner E2E, esses arquivos permanecem no workspace entre execuções. O log continua sendo gravado em `e2e_run.log`, salvo quando outro caminho é informado com `--log`.

## Fluxo financeiro

```text
get_payment_instructions
 -> Mini Bank POST /charges
 -> Mini Pix POST /charges
 -> authorize_payment
 -> Mini Bank POST /payments/pix
 -> Mini Pix POST /resolve, /complete e /invoices
 -> confirm_order
 -> Mini Bank GET /charges/{pix_code}
```

O pedido só é confirmado se o pagamento pertencer ao checkout, estiver pago e tiver o mesmo valor do checkout.

## Dados de catálogo

Os produtos iniciais estão em [src/agent_economy_e2e/ecommerce/database/seed_catalog.json](src/agent_economy_e2e/ecommerce/database/seed_catalog.json). O catálogo inclui Tênis X, Camiseta Básica, Mochila Urban e um produto indisponível.

## Testes

Execute todos os testes com:

```bash
uv run pytest
```

Os testes cobrem catálogo, carrinho, checkout, pagamento, pedidos, integração financeira e registro das tools MCP.

## Dashboard Streamlit

Execute `uv run streamlit run src/agent_economy_e2e/app.py` e use **Executar teste E2E** na barra lateral. A linha do tempo e os painéis são atualizados enquanto o runner avança pelas etapas; os dados continuam disponíveis em `data/`.
