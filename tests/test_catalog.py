from agent_economy_e2e.ecommerce.app import EcommerceApp


def test_search_products(app: EcommerceApp) -> None:
    result = app.catalog.search(query="Tênis")
    assert len(result.products) == 1
    product = result.products[0]
    assert product.id == "prod_tenis_x"
    assert product.price == 799.9
    assert product.currency == "BRL"
    assert product.available is True
    assert product.variants


def test_search_products_accepts_plural_and_unaccented_terms(app: EcommerceApp) -> None:
    result = app.catalog.search(query="  mochilas   urban ")
    assert [product.id for product in result.products] == ["prod_mochila_urban"]


def test_search_products_paginates_with_cursor(app: EcommerceApp) -> None:
    first = app.catalog.search(limit=1, sort="name_asc")
    assert len(first.products) == 1
    assert first.next_cursor is not None
    second = app.catalog.search(limit=1, sort="name_asc", cursor=first.next_cursor)
    assert len(second.products) == 1
    assert first.products[0].id != second.products[0].id
