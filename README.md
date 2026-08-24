# Agent Economy E2E Sandbox

Sandbox de ecommerce orientado a agentes, implementado em Python. O objetivo é
demonstrar uma compra completa entre agentes e serviços MCP, incluindo catálogo,
carrinho, checkout, políticas de pagamento, débito PIX e confirmação do pedido.
O fluxo principal apresenta no terminal, com Rich, o que cada componente está
fazendo e os dados essenciais de cada etapa.

O projeto inclui uma infraestrutura financeira local composta por Mini Bank,
Mini Pix e Payment Gateway. A persistência é feita em arquivos JSON.

A especificação resumida dos componentes, contratos e fluxos está em
[architecture.md](architecture.md).

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

O Payment Gateway MCP registra duas tools:

| Tool                | Função                                                        |
| ------------------- | ------------------------------------------------------------- |
| `evaluate_payment`  | Avalia a política e informa se é necessária aprovação humana. |
| `authorize_payment` | Autoriza um pagamento PIX através do Mini Bank.               |

O método de pagamento aceito pelo checkout MCP é `pix`.

## Modos de execução

### 1. Demonstração do sandbox

Esse é o fluxo principal e o único entrypoint da aplicação. O `main.py` inicia
os clientes dos MCPs Ecommerce e Payment Gateway, configura o agente LangGraph
e executa a compra com logs Rich no terminal.

Antes de executar, inicie a infraestrutura financeira com Docker Compose:

```bash
docker compose up --build -d
```

Depois execute um pedido:

```bash
uv run app "Compre um Tenis X tamanho 42"
```

Também é possível executar o mesmo entrypoint pelo módulo Python:

```bash
uv run python -m agent_economy_e2e "quero comprar 2 mochilas urban e 2 tenis x"
```

O agente usa, por padrão, a conta `buyer`, o endereço de teste e o modelo
Ollama `qwen3:1.7b`. O modelo precisa estar instalado e o Ollama em execução:

```bash
ollama serve
ollama pull qwen3:1.7b
```

Opções disponíveis:

```bash
uv run app "Compre um Tenis X" --payer-account-id buyer
uv run app "Compre um Tenis X" --agent-id default
uv run app "Compre um Tenis X" --address '{"street":"Rua A","number":"10","city":"Sao Paulo","state":"SP","postal_code":"01000-000","country":"BR"}'
```

O fluxo executado é:

```text
pedido do usuario
 -> planejamento pelo agente
 -> busca de produtos
 -> carrinho
 -> calculo de subtotal, frete e total
 -> checkout
 -> cobranca Mini Pix
 -> avaliacao do Payment Gateway
 -> aprovacao humana, quando exigida
 -> debito no Mini Bank
 -> confirmacao do pedido
```

### 2. Servidor Ecommerce MCP isolado

Use este modo para conectar um cliente MCP diretamente ao domínio de ecommerce,
sem executar o agente de compra:

```bash
uv run ecommerce-mcp
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

### 3. Infraestrutura financeira manual

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

Use este modo quando os serviços financeiros precisarem ser executados fora do
Docker Compose, em terminais separados:

### 4. Docker Compose

Suba o Mini Pix e o Mini Bank com os dados persistidos na raiz do projeto:

```bash
docker compose up --build -d
```

As APIs ficam disponíveis em `http://localhost:8001` (Mini Pix) e
`http://localhost:8000` (Mini Bank). Para parar os containers:

```bash
docker compose down
```

## Configuração

| Variável                   | Uso                                          | Padrão                  |
| -------------------------- | -------------------------------------------- | ----------------------- |
| `ECOMMERCE_DATA_DIR`       | Diretório dos JSONs do Ecommerce MCP.        | `data/ecommerce`        |
| `MINI_BANK_DATA_DIR`       | Diretório dos JSONs do Mini Bank.            | `data/mini-bank`        |
| `MINI_PIX_DATA_DIR`        | Diretório dos JSONs do Mini Pix.             | `data/mini-pix`         |
| `MINI_BANK_URL`            | URL do Mini Bank usada pelo Gateway MCP.     | Definida pelo ambiente  |
| `MINI_PIX_URL`             | URL financeira usada pelos serviços.         | `http://127.0.0.1:8001` |
| `PAYMENT_GATEWAY_DATA_DIR` | Diretório do cadastro de agentes do Gateway. | `data/payment-gateway`  |

Na execução manual, mantenha `MINI_BANK_URL` apontando para o Mini Bank e
`MINI_PIX_URL` apontando para o Mini Pix nos serviços correspondentes.

## Persistência

O Ecommerce MCP grava coleções como `catalog.json`, `carts.json`, `checkouts.json`, `payments.json` e `orders.json` em `data/ecommerce` por padrão.

O Mini Bank grava `accounts.json` em `data/mini-bank`, e o Mini Pix grava `charges.json`, `transactions.json` e `invoices.json` em `data/mini-pix`. Os caminhos podem ser substituídos pelas variáveis de ambiente correspondentes.

O Payment Gateway grava `agents.json` em `data/payment-gateway`. Cada registro contém `agent_id`, `account_id`, `max_expeding_value`, `permited_categories`, `require_human_approval` e `human_approval_threshold`. Quando `require_human_approval` é `true`, toda compra exige aprovação humana. `human_approval_threshold` aceita um valor numérico para exigir aprovação acima desse valor, `true` para encaminhar toda compra ao humano e `false` para bloquear a compra por padrão. Quando a compra excede `max_expeding_value` e a aprovação humana está habilitada, o gateway solicita uma exceção ao humano; com aprovação, a transação pode prosseguir. `null` mantém o comportamento automático legado, desde que as demais regras sejam válidas. A aprovação humana recebe uma pergunta explícita de sim/não, itens, total, método, PIX, motivo e o objeto completo do checkout. Antes de encaminhar um PIX ao Mini Bank, o Gateway confirma a associação agente-conta, o limite do pagamento e as categorias permitidas.

Esses arquivos permanecem no workspace entre execuções. Para uma demonstração
repetível, use diretórios de dados limpos ou restaure os JSONs de exemplo.

## Fluxo financeiro

```text
get_payment_instructions
 -> Mini Bank POST /charges
 -> Mini Pix POST /charges
 -> evaluate_payment
 -> aprovação humana (quando exigida pela política)
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

## Agente e políticas de pagamento

O pacote `agent_economy_e2e.agent` implementa o fluxo de compra com LangGraph. O
LLM interpreta o pedido, enquanto o grafo controla a ordem das tools MCP e pausa
antes do débito PIX para aprovação explícita. Quando já existe um carrinho ativo
com itens, o agente também pausa para permitir continuar, alterar quantidades,
remover itens ou limpar o carrinho antes de adicionar a nova compra.

O pacote `agent_economy_e2e.agent` contém a configuração do agente e o grafo
LangGraph. A execução e a apresentação ficam em `agent_economy_e2e.main`.

O agente pesquisa cada produto no Ecommerce MCP, monta o carrinho, cria o
checkout, chama o Payment Gateway MCP e pausa para aprovação antes do débito
PIX. O Gateway valida a associação agente-conta, o limite, as categorias e as
regras de aprovação humana. O pedido só é confirmado depois que o pagamento
pertencente ao checkout é reconciliado.

É possível trocar o modelo e a URL com `OLLAMA_MODEL` e `OLLAMA_BASE_URL`.
