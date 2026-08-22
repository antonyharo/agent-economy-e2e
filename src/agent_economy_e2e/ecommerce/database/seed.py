from __future__ import annotations

import json
from pathlib import Path

SEED_CATALOG_PATH = Path(__file__).with_name("seed_catalog.json")


def ensure_seed_data(data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    catalog_path = data_dir / "catalog.json"
    if catalog_path.exists():
        return
    products = json.loads(SEED_CATALOG_PATH.read_text(encoding="utf-8"))
    catalog_path.write_text(
        json.dumps(products, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    for name, default in (
        ("carts", []),
        ("checkouts", []),
        ("payments", []),
        ("orders", []),
    ):
        path = data_dir / f"{name}.json"
        if not path.exists():
            path.write_text(json.dumps(default, indent=2), encoding="utf-8")
