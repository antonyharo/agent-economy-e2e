# Arquitetura

## Objetivo

O projeto é um sandbox de economia entre agentes. Ele demonstra um agente de compras que conversa com serviços MCP, calcula o pedido no Ecommerce, valida políticas financeiras e conclui um pagamento PIX somente após aprovação e reconciliação.

## Ecommerce MCP

Transporte: MCP via stdio. Persistência: `data/ecommerce/*.json`.

* `search_products(query, filters, sort, limit, cursor)`: pesquisa produtos no catálogo. Retorna produtos, variantes e cursor de paginação.
* `get_cart()`: consulta o carrinho ativo. Retorna o carrinho e seus itens.
* `create_cart()`: cria um carrinho ativo. Retorna o carrinho criado.
* `add_to_cart(product_id, quantity, variant_id)`: adiciona um produto disponível. Retorna o carrinho atualizado.
* `update_cart_item(product_id, quantity, variant_id)`: altera a quantidade de um item. Retorna o carrinho atualizado.
* `remove_from_cart(product_id, variant_id)`: remove um item. Retorna o carrinho atualizado.
* `clear_cart()`: remove todos os itens. Retorna o carrinho vazio.
* `calculate_cart()`: calcula valores no servidor. Retorna subtotal, frete, desconto, total e itens.
* `create_checkout(cart_id, shipping_address, shipping_option, payment_method)`: cria um snapshot do carrinho. Retorna checkout, totais e status de pagamento pendente.
* `get_payment_instructions(checkout_id)`: cria ou recupera uma cobrança PIX. Retorna `payment_id`, `pix_code`, `transaction_id`, valor e moeda.
* `confirm_order(checkout_id, payment_id, shipping_address)`: confirma o pedido se o pagamento reconciliado corresponder ao checkout. Retorna o pedido confirmado.

## Payment Gateway MCP

Transporte: MCP via stdio. Persistência: `data/payment-gateway/agents.json`.

* `evaluate_payment(payer_account_id, amount, agent_id, categories)`: valida agente, conta, limite e categorias. Retorna se a compra foi aprovada e se exige aprovação humana.
* `authorize_payment(payer_account_id, pix_code, amount, reference_id, agent_id, categories, human_approved)`: valida a política e encaminha o débito ao Mini Bank. Retorna pagamento, invoice e transação aprovados.

## Mini Bank API

Transporte: HTTP. Padrão: `[http://127.0.0.1:8000](http://127.0.0.1:8000)`. Persistência: `data/mini-bank/accounts.json`.

* `GET /accounts/{account_id}/balance`: consulta saldo e moeda. Retorna conta e saldo.
* `POST /accounts/debit` com `account_id`, `amount` e `transaction_id`: debita uma conta. Retorna conta atualizada.
* `POST /accounts/credit` com `account_id`, `amount` e `transaction_id`: credita uma conta. Retorna conta atualizada.
* `POST /charges(receiver_account_id, amount)`: solicita uma cobrança PIX ao Mini Pix. Retorna o código PIX, transaction id e valor.
* `GET /charges/{pix_code}`: consulta uma cobrança PIX no Mini Pix. Retorna status, recebedor, valor e transação.
* `POST /payments/pix(pix_code, payer_account_id, amount)`: valida a cobrança, debita o pagador, credita o recebedor e conclui a transação. Retorna a invoice.

## Mini Pix API

Transporte: HTTP. Padrão: `[http://127.0.0.1:8001](http://127.0.0.1:8001)`. Persistência: `data/mini-pix/charges.json`, `transactions.json` e `invoices.json`.

* `POST /charges(txid, receiver_account_id, amount)`: cria uma cobrança PIX. Retorna `pix_code`, `charge_id`, transação e status pendente.
* `POST /resolve(pix_code)`: resolve um código PIX. Retorna a cobrança.
* `POST /complete(transaction_id)`: marca a transação como concluída. Retorna a transação.
* `POST /fail(transaction_id)`: marca a transação como falha. Retorna a transação.
* `POST /invoices(transaction_id)`: gera ou recupera uma invoice de transação concluída. Retorna invoice, valor e status.

## Arquitetura e comunicação

```text
Usuário
  |
  v
main.py (CLI, Rich e ciclo da demonstração)
  |
  v
Agente LangGraph (agent/agent.py + agent/graph.py)
  |
  +-- MCPToolset -- stdio --> Ecommerce MCP
  |                              |
  |                              +--> JSON Store do Ecommerce
  |                              +--> Mini Bank API (/charges)
  |
  +-- MCPToolset -- stdio --> Payment Gateway MCP
                                 |
                                 +--> Payment Gateway
                                         |
                                         +--> Mini Bank API
                                                 |
                                                 +--> Mini Pix API

```

`main.py` inicia as sessões MCP e configura o agente. O grafo decide a ordem das operações, mas não define preços nem debita diretamente contas. O Ecommerce calcula os totais. O Gateway aplica as políticas do agente. O Mini Bank movimenta saldos e delega o ciclo PIX ao Mini Pix. A confirmação do pedido acontece somente depois da reconciliação do pagamento.

## Fluxo real

Entrada do usuário:

```text
"quero comprar 2 tênis x"

```

1. `main.py` recebe o texto e inicia as sessões MCP.
2. O LLM interpreta a solicitação e identifica `Tênis X`, quantidade `2` e, se informado, a variante.
3. O agente chama `search_products(query="Tênis X")` no Ecommerce MCP.
4. O agente cria ou reutiliza o carrinho com `get_cart()` e `create_cart()`, depois chama `add_to_cart(product_id, quantity=2)`.
5. `calculate_cart()` calcula subtotal, frete, desconto e total no servidor.
6. `create_checkout(...)` cria o checkout com endereço e pagamento `pix`.
7. `get_payment_instructions(checkout_id)` faz o Ecommerce solicitar ao Mini Bank uma cobrança.
8. O Mini Bank chama o Mini Pix em `POST /charges`; o Mini Pix cria o PIX e retorna `pix_code` e `transaction_id`.
9. O agente chama `evaluate_payment(...)` no Gateway. Se necessário, `main.py` pede aprovação humana no terminal.
10. Após a aprovação, o agente chama `authorize_payment(...)`.
11. O Gateway chama `POST /payments/pix` no Mini Bank. O Mini Bank resolve o PIX no Mini Pix, debita o comprador, credita o vendedor, chama `POST /complete` e gera a invoice.
12. O agente chama `confirm_order(...)` no Ecommerce. O pedido é confirmado somente com pagamento válido, pago e de valor igual ao checkout.