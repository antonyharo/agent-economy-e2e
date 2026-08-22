from pathlib import Path

import pytest

from agent_economy_e2e.ecommerce.app import EcommerceApp, create_app


@pytest.fixture
def app(tmp_path: Path) -> EcommerceApp:
    return create_app(tmp_path)
